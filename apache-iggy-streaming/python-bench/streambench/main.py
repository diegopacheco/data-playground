import os

from streambench import iggy_bench, kafka_bench
from streambench.config import BenchConfig
from streambench.payload import now_us
from streambench.result import build, render


def main() -> None:
    cfg = BenchConfig.from_env(os.environ)
    runner = iggy_bench.run if cfg.broker == "iggy" else kafka_bench.run
    producer, recorder = runner(cfg)
    print(render(build(cfg, producer, recorder, now_us())), flush=True)


if __name__ == "__main__":
    main()
