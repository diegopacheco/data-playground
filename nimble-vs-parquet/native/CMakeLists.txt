add_executable(nimble_bench nimble_bench.cpp)
target_link_libraries(
  nimble_bench
  nimble_velox_writer
  nimble_velox_reader
  nimble_tablet_reader
  velox_file
  velox_memory
  velox_vector
  velox_dwio_common
  Folly::folly
)
