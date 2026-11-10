import sys
import time
from collections.abc import Iterable

from pyflink.common import Row, Types, WatermarkStrategy
from pyflink.datastream import KeyedProcessFunction, MapFunction, RuntimeContext, StreamExecutionEnvironment
from pyflink.datastream.connectors.number_seq import NumberSequenceSource
from pyflink.datastream.state import ValueState, ValueStateDescriptor

from clicks_py.model import JobArgs, line, next_count, parse_args, user_for

SEQUENCE_END = 1_000_000_000_000


class ClickCounter(KeyedProcessFunction):
    def __init__(self, version: str) -> None:
        self.version = version
        self.count: ValueState | None = None

    def open(self, runtime_context: RuntimeContext) -> None:
        self.count = runtime_context.get_state(ValueStateDescriptor("count", Types.LONG()))

    def process_element(self, value: Row, ctx: KeyedProcessFunction.Context) -> Iterable[str]:
        assert self.count is not None
        user, seq = value[0], value[1]
        current = next_count(self.count.value())
        self.count.update(current)
        yield line("python", self.version, user, seq, current)


class Throttle(MapFunction):
    def __init__(self, users: int, rate: int) -> None:
        self.users = users
        self.pause = 1.0 / rate

    def map(self, value: int) -> Row:
        time.sleep(self.pause)
        return Row(user_for(value, self.users), value)


def build(env: StreamExecutionEnvironment, args: JobArgs) -> None:
    (
        env.from_source(NumberSequenceSource(0, SEQUENCE_END), WatermarkStrategy.no_watermarks(), "clicks-source")
        .uid("clicks-source")
        .map(Throttle(args.users, args.rate), output_type=Types.ROW([Types.STRING(), Types.LONG()]))
        .uid("clicks-to-user")
        .name("clicks-to-user")
        .key_by(lambda row: row[0], key_type=Types.STRING())
        .process(ClickCounter(args.version), output_type=Types.STRING())
        .uid("click-counter")
        .name("click-counter")
        .print()
        .uid("clicks-print")
    )


def main() -> None:
    env = StreamExecutionEnvironment.get_execution_environment()
    build(env, parse_args(sys.argv[1:]))
    env.execute("clicks-python")


if __name__ == "__main__":
    main()
