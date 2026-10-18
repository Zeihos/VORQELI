import pytest
from vorqeli_connect.recovery import RecoveryPolicy


def test_bounded_retry_schedule():
    recovery = RecoveryPolicy((3, 7))
    assert not recovery.observe(wanted=True, unhealthy=True, busy=False, now=0)
    assert recovery.status(1).next_in_seconds == 2
    assert not recovery.observe(wanted=True, unhealthy=True, busy=True, now=4)
    assert recovery.observe(wanted=True, unhealthy=True, busy=False, now=5)
    assert recovery.status(5).attempts == 1
    assert not recovery.observe(wanted=True, unhealthy=True, busy=False, now=6)
    assert recovery.observe(wanted=True, unhealthy=True, busy=False, now=12)
    assert recovery.status(12).exhausted
    assert not recovery.observe(wanted=True, unhealthy=True, busy=False, now=200)


def test_reconnect_stops_when_user_off():
    recovery = RecoveryPolicy((1,))
    recovery.observe(wanted=True, unhealthy=True, busy=False, now=0)
    assert not recovery.observe(wanted=False, unhealthy=True, busy=False, now=2)
    assert recovery.status(2).attempts == 0
    assert recovery.status(2).next_in_seconds is None
    assert not recovery.observe(wanted=True, unhealthy=True, busy=False, now=3)
    assert recovery.observe(wanted=True, unhealthy=True, busy=False, now=4)


def test_healthy_resets_retry_budget():
    recovery = RecoveryPolicy((1,))
    recovery.observe(wanted=True, unhealthy=True, busy=False, now=0)
    assert recovery.observe(wanted=True, unhealthy=True, busy=False, now=2)
    assert not recovery.observe(wanted=True, unhealthy=False, busy=False, now=3)
    assert not recovery.status(3).exhausted


def test_bad_policy_rejected():
    with pytest.raises(ValueError): RecoveryPolicy(())
    with pytest.raises(ValueError): RecoveryPolicy((1, 0))
