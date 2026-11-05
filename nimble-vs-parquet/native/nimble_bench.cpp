#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <folly/init/Init.h>

#include "dwio/nimble/tablet/Constants.h"
#include "dwio/nimble/tablet/TabletReader.h"
#include "dwio/nimble/velox/VeloxReader.h"
#include "dwio/nimble/writer/VeloxWriter.h"
#include "velox/common/file/LocalFile.h"
#include "velox/common/memory/Memory.h"
#include "velox/dwio/common/ColumnSelector.h"
#include "velox/vector/ComplexVector.h"
#include "velox/vector/DecodedVector.h"
#include "velox/vector/FlatVector.h"

using namespace facebook;

namespace {

constexpr uint64_t kBatchRows = 1 << 20;

struct Table {
  uint64_t rows{0};
  std::vector<std::string> names;
  std::vector<std::string> kinds;
};

struct Pools {
  std::shared_ptr<velox::memory::MemoryPool> root;
  std::shared_ptr<velox::memory::MemoryPool> leaf;
};

double nowMs() {
  return std::chrono::duration<double, std::milli>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

uint64_t splitmix(uint64_t x) {
  x += 0x9E3779B97F4A7C15ULL;
  x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
  x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
  return x ^ (x >> 31);
}

uint64_t stringHash(std::string_view s) {
  uint64_t h = splitmix(s.size());
  for (uint64_t j = 0; j < s.size(); ++j) {
    h += splitmix((static_cast<uint64_t>(static_cast<uint8_t>(s[j])) << 32) | j);
  }
  return h;
}

std::string readAll(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("cannot open " + path);
  }
  std::ostringstream out;
  out << in.rdbuf();
  return out.str();
}

void writeAll(const std::string& path, const void* data, size_t size) {
  std::ofstream out(path, std::ios::binary);
  out.write(static_cast<const char*>(data), size);
  if (!out) {
    throw std::runtime_error("cannot write " + path);
  }
}

Table readSchema(const std::string& dir) {
  std::ifstream in(dir + "/schema.txt");
  if (!in) {
    throw std::runtime_error("missing " + dir + "/schema.txt");
  }
  Table table;
  std::string word;
  in >> word >> table.rows;
  std::string name;
  std::string kind;
  while (in >> name >> kind) {
    table.names.push_back(name);
    table.kinds.push_back(kind);
  }
  return table;
}

velox::TypePtr veloxType(const std::string& kind) {
  if (kind == "bigint") {
    return velox::BIGINT();
  }
  if (kind == "double") {
    return velox::DOUBLE();
  }
  if (kind == "varchar") {
    return velox::VARCHAR();
  }
  throw std::runtime_error("unknown type " + kind);
}

std::string kindOf(const velox::TypePtr& type) {
  switch (type->kind()) {
    case velox::TypeKind::BIGINT:
      return "bigint";
    case velox::TypeKind::DOUBLE:
      return "double";
    case velox::TypeKind::VARCHAR:
      return "varchar";
    default:
      throw std::runtime_error("unsupported type " + type->toString());
  }
}

velox::RowTypePtr rowType(const Table& table) {
  std::vector<velox::TypePtr> types;
  for (const auto& kind : table.kinds) {
    types.push_back(veloxType(kind));
  }
  return velox::ROW(std::vector<std::string>(table.names), std::move(types));
}

template <typename T>
velox::VectorPtr loadFixed(
    const std::string& path,
    uint64_t rows,
    const velox::TypePtr& type,
    velox::memory::MemoryPool* pool) {
  auto bytes = readAll(path);
  if (bytes.size() != rows * sizeof(T)) {
    throw std::runtime_error("bad size " + path);
  }
  auto vector = velox::BaseVector::create<velox::FlatVector<T>>(type, rows, pool);
  std::memcpy(vector->mutableRawValues(), bytes.data(), bytes.size());
  return vector;
}

velox::VectorPtr loadStrings(
    const std::string& base,
    uint64_t rows,
    velox::memory::MemoryPool* pool) {
  auto offsetBytes = readAll(base + ".off");
  auto data = readAll(base + ".bin");
  if (offsetBytes.size() != (rows + 1) * sizeof(int64_t)) {
    throw std::runtime_error("bad offsets " + base);
  }
  std::vector<int64_t> offsets(rows + 1);
  std::memcpy(offsets.data(), offsetBytes.data(), offsetBytes.size());
  auto buffer = velox::AlignedBuffer::allocate<char>(data.size() + 1, pool);
  std::memcpy(buffer->asMutable<char>(), data.data(), data.size());
  const char* chars = buffer->as<char>();
  auto vector = velox::BaseVector::create<velox::FlatVector<velox::StringView>>(
      velox::VARCHAR(), rows, pool);
  vector->addStringBuffer(buffer);
  for (uint64_t i = 0; i < rows; ++i) {
    vector->setNoCopy(
        i,
        velox::StringView(chars + offsets[i], offsets[i + 1] - offsets[i]));
  }
  return vector;
}

velox::RowVectorPtr loadTable(
    const std::string& dir,
    const Table& table,
    velox::memory::MemoryPool* pool) {
  std::vector<velox::VectorPtr> children;
  for (size_t c = 0; c < table.names.size(); ++c) {
    auto base = dir + "/c" + std::to_string(c);
    const auto& kind = table.kinds[c];
    if (kind == "bigint") {
      children.push_back(loadFixed<int64_t>(base + ".bin", table.rows, velox::BIGINT(), pool));
    } else if (kind == "double") {
      children.push_back(loadFixed<double>(base + ".bin", table.rows, velox::DOUBLE(), pool));
    } else {
      children.push_back(loadStrings(base, table.rows, pool));
    }
  }
  return std::make_shared<velox::RowVector>(
      pool, rowType(table), nullptr, table.rows, std::move(children));
}

std::shared_ptr<const nimble::TabletReader> openTablet(
    const std::string& path,
    velox::memory::MemoryPool* pool) {
  nimble::TabletReader::Options options;
  options.preloadOptionalSections = {std::string(nimble::kSchemaSection)};
  options.ioOptions.emplace(pool)
      .setMetadataIoStats(std::make_shared<velox::io::IoStatistics>())
      .setIndexIoStats(std::make_shared<velox::io::IoStatistics>());
  return nimble::TabletReader::create(
      std::make_shared<velox::LocalReadFile>(path), pool, options);
}

std::shared_ptr<velox::dwio::common::ColumnSelector> selectorFor(
    const Table& table,
    const std::vector<std::string>& columns) {
  auto type = rowType(table);
  if (columns.empty()) {
    return std::make_shared<velox::dwio::common::ColumnSelector>(type);
  }
  return std::make_shared<velox::dwio::common::ColumnSelector>(type, columns);
}

struct ColumnSum {
  std::string name;
  uint64_t sum{0};
};

void accumulate(const velox::VectorPtr& vector, uint64_t firstRow, uint64_t& sum) {
  velox::DecodedVector decoded(*vector);
  auto size = vector->size();
  for (velox::vector_size_t i = 0; i < size; ++i) {
    uint64_t bits = 0;
    if (decoded.isNullAt(i)) {
      throw std::runtime_error("unexpected null");
    }
    switch (vector->typeKind()) {
      case velox::TypeKind::BIGINT:
        bits = static_cast<uint64_t>(decoded.valueAt<int64_t>(i));
        break;
      case velox::TypeKind::DOUBLE: {
        double value = decoded.valueAt<double>(i);
        std::memcpy(&bits, &value, sizeof(bits));
        break;
      }
      case velox::TypeKind::VARCHAR: {
        auto value = decoded.valueAt<velox::StringView>(i);
        bits = stringHash(std::string_view(value.data(), value.size()));
        break;
      }
      default:
        throw std::runtime_error("unsupported type");
    }
    sum += splitmix(bits + firstRow + i);
  }
}

uint64_t readAllRows(nimble::VeloxReader& reader) {
  velox::VectorPtr result;
  uint64_t rows = 0;
  while (reader.next(kBatchRows, result)) {
    rows += result->size();
  }
  return rows;
}

std::vector<std::string> splitColumns(const std::string& arg) {
  std::vector<std::string> columns;
  std::stringstream in(arg);
  std::string item;
  while (std::getline(in, item, ',')) {
    if (!item.empty()) {
      columns.push_back(item);
    }
  }
  return columns;
}

std::string jsonList(const std::vector<double>& values) {
  std::ostringstream out;
  out << "[";
  for (size_t i = 0; i < values.size(); ++i) {
    out << (i ? "," : "") << values[i];
  }
  out << "]";
  return out.str();
}

int cmdWrite(const Pools& pools, const std::string& src, const std::string& out, int iterations) {
  auto table = readSchema(src);
  auto data = loadTable(src, table, pools.leaf.get());
  std::vector<double> times;
  for (int i = 0; i < iterations; ++i) {
    std::filesystem::remove(out);
    double start = nowMs();
    nimble::VeloxWriter writer(
        data->type(),
        std::make_unique<velox::LocalWriteFile>(out),
        *pools.root,
        nimble::VeloxWriterOptions{});
    writer.write(data);
    writer.close();
    times.push_back(nowMs() - start);
  }
  std::cout << "{\"write_ms\":" << jsonList(times)
            << ",\"size_bytes\":" << std::filesystem::file_size(out)
            << ",\"rows\":" << table.rows
            << ",\"columns\":" << table.names.size() << "}" << std::endl;
  return 0;
}

int cmdScan(
    const Pools& pools,
    const std::string& src,
    const std::string& file,
    int iterations,
    const std::vector<std::string>& columns) {
  auto table = readSchema(src);
  std::vector<double> times;
  uint64_t rows = 0;
  for (int i = 0; i < iterations; ++i) {
    double start = nowMs();
    nimble::VeloxReader reader(
        openTablet(file, pools.leaf.get()), *pools.leaf, selectorFor(table, columns));
    rows = readAllRows(reader);
    times.push_back(nowMs() - start);
  }
  auto names = columns.empty() ? table.names : columns;
  auto type = rowType(table);
  std::vector<ColumnSum> sums;
  for (const auto& name : names) {
    sums.push_back({name, 0});
  }
  nimble::VeloxReader reader(
      openTablet(file, pools.leaf.get()), *pools.leaf, selectorFor(table, columns));
  velox::VectorPtr result;
  uint64_t seen = 0;
  while (reader.next(kBatchRows, result)) {
    auto row = std::dynamic_pointer_cast<velox::RowVector>(result);
    for (auto& sum : sums) {
      accumulate(row->childAt(type->getChildIdx(sum.name)), seen, sum.sum);
    }
    seen += row->size();
  }
  std::cout << "{\"scan_ms\":" << jsonList(times) << ",\"rows\":" << rows
            << ",\"columns\":" << names.size() << ",\"checksums\":{";
  for (size_t i = 0; i < sums.size(); ++i) {
    std::cout << (i ? "," : "") << "\"" << sums[i].name << "\":\"" << sums[i].sum << "\"";
  }
  std::cout << "}}" << std::endl;
  return 0;
}

int cmdMeta(const Pools& pools, const std::string& file, int iterations) {
  std::vector<double> times;
  size_t columns = 0;
  for (int i = 0; i < iterations; ++i) {
    double start = nowMs();
    nimble::VeloxReader reader(openTablet(file, pools.leaf.get()), *pools.leaf);
    columns = reader.type()->size();
    times.push_back(nowMs() - start);
  }
  auto tablet = openTablet(file, pools.leaf.get());
  uint64_t schemaBytes = 0;
  uint64_t optionalBytes = 0;
  for (const auto& [name, section] : tablet->optionalSections()) {
    optionalBytes += section.size();
    if (name == nimble::kSchemaSection) {
      schemaBytes = section.size();
    }
  }
  uint64_t stripeBytes = 0;
  if (auto stripes = tablet->stripesMetadata()) {
    stripeBytes += stripes->size();
  }
  for (const auto& group : tablet->stripeGroupsMetadata()) {
    stripeBytes += group.size();
  }
  std::cout << "{\"meta_ms\":" << jsonList(times)
            << ",\"columns\":" << columns
            << ",\"footer_bytes\":" << tablet->footerSize()
            << ",\"schema_bytes\":" << schemaBytes
            << ",\"stripe_metadata_bytes\":" << stripeBytes
            << ",\"metadata_bytes\":" << tablet->footerSize() + stripeBytes + optionalBytes
            << ",\"stripes\":" << tablet->stripeCount()
            << ",\"file_bytes\":" << tablet->fileSize() << "}" << std::endl;
  return 0;
}

void dumpColumn(const velox::VectorPtr& vector, const std::string& base, std::string& fixed, std::vector<int64_t>& offsets) {
  velox::DecodedVector decoded(*vector);
  for (velox::vector_size_t i = 0; i < vector->size(); ++i) {
    switch (vector->typeKind()) {
      case velox::TypeKind::BIGINT: {
        int64_t value = decoded.valueAt<int64_t>(i);
        fixed.append(reinterpret_cast<const char*>(&value), sizeof(value));
        break;
      }
      case velox::TypeKind::DOUBLE: {
        double value = decoded.valueAt<double>(i);
        fixed.append(reinterpret_cast<const char*>(&value), sizeof(value));
        break;
      }
      default: {
        auto value = decoded.valueAt<velox::StringView>(i);
        fixed.append(value.data(), value.size());
        offsets.push_back(static_cast<int64_t>(fixed.size()));
      }
    }
  }
}

int cmdDump(const Pools& pools, const std::string& file, const std::string& out) {
  nimble::VeloxReader reader(openTablet(file, pools.leaf.get()), *pools.leaf);
  auto type = reader.type();
  std::vector<std::string> data(type->size());
  std::vector<std::vector<int64_t>> offsets(type->size(), std::vector<int64_t>{0});
  velox::VectorPtr result;
  uint64_t rows = 0;
  while (reader.next(kBatchRows, result)) {
    auto row = std::dynamic_pointer_cast<velox::RowVector>(result);
    for (size_t c = 0; c < type->size(); ++c) {
      dumpColumn(row->childAt(c), out, data[c], offsets[c]);
    }
    rows += row->size();
  }
  std::filesystem::create_directories(out);
  std::ofstream schema(out + "/schema.txt");
  schema << "rows " << rows << "\n";
  for (size_t c = 0; c < type->size(); ++c) {
    auto kind = kindOf(type->childAt(c));
    schema << type->nameOf(c) << " " << kind << "\n";
    auto base = out + "/c" + std::to_string(c);
    writeAll(base + ".bin", data[c].data(), data[c].size());
    if (kind == "varchar") {
      writeAll(base + ".off", offsets[c].data(), offsets[c].size() * sizeof(int64_t));
    }
  }
  std::cout << "{\"rows\":" << rows << ",\"columns\":" << type->size() << "}" << std::endl;
  return 0;
}

int usage() {
  std::cerr << "usage: nimble_bench version | write SRC OUT N | scan SRC FILE N [COLS] | meta FILE N | dump FILE OUT" << std::endl;
  return 2;
}

}

int main(int argc, char** argv) {
  int fakeArgc = 1;
  folly::Init init(&fakeArgc, &argv, false);
  std::vector<std::string> args(argv + 1, argv + argc);
  if (args.empty()) {
    return usage();
  }
  if (args[0] == "version") {
    std::cout << "nimble_bench ok" << std::endl;
    return 0;
  }
  velox::memory::MemoryManager::initialize(velox::memory::MemoryManager::Options{});
  Pools pools;
  pools.root = velox::memory::memoryManager()->addRootPool("nimble_bench");
  pools.leaf = pools.root->addLeafChild("nimble_bench_leaf");
  try {
    if (args[0] == "write" && args.size() == 4) {
      return cmdWrite(pools, args[1], args[2], std::stoi(args[3]));
    }
    if (args[0] == "scan" && (args.size() == 4 || args.size() == 5)) {
      return cmdScan(pools, args[1], args[2], std::stoi(args[3]), args.size() == 5 ? splitColumns(args[4]) : std::vector<std::string>{});
    }
    if (args[0] == "meta" && args.size() == 3) {
      return cmdMeta(pools, args[1], std::stoi(args[2]));
    }
    if (args[0] == "dump" && args.size() == 3) {
      return cmdDump(pools, args[1], args[2]);
    }
  } catch (const std::exception& e) {
    std::cerr << "error: " << e.what() << std::endl;
    return 1;
  }
  return usage();
}
