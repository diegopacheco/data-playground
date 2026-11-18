import pytest

from streamjob.args import parse


def test_the_trigger_interval_is_the_only_knob_the_sweep_turns_so_it_must_reach_the_job() -> None:
    args = parse(["--table", "lake.db.t", "--checkpoint", "s3a://c/t", "--trigger-seconds", "15"])
    assert args.trigger_seconds == 15
    assert args.table == "lake.db.t"
    assert args.checkpoint == "s3a://c/t"
    assert args.starting_offsets == "latest"
    assert args.topic == "events"


def test_a_job_without_its_own_checkpoint_cannot_recover_so_it_refuses_to_start() -> None:
    with pytest.raises(SystemExit):
        parse(["--table", "lake.db.t"])


def test_a_zero_trigger_would_be_an_unbounded_batch_loop_and_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse(["--table", "t", "--checkpoint", "c", "--trigger-seconds", "0"])
