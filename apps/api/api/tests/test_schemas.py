from datetime import UTC, datetime

from api.schemas import UTCModel


def test_utc_model_stamps_top_level_naive_datetime():
    class SimpleModel(UTCModel):
        dt: datetime

    naive = datetime(2026, 5, 21, 10, 0, 0)
    assert naive.tzinfo is None

    model = SimpleModel(dt=naive)
    assert model.dt.tzinfo == UTC
    assert model.dt.hour == 10


def test_utc_model_preserves_aware_datetime():
    class SimpleModel(UTCModel):
        dt: datetime

    aware = datetime(2026, 5, 21, 10, 0, 0, tzinfo=UTC)
    model = SimpleModel(dt=aware)
    assert model.dt.tzinfo == UTC


def test_utc_model_nested_behavior():
    class ChildModel(UTCModel):
        dt: datetime

    class ParentModel(UTCModel):
        child: ChildModel
        children: list[ChildModel]

    naive = datetime(2026, 5, 21, 10, 0, 0)
    child1 = ChildModel(dt=naive)
    child2 = ChildModel(dt=naive)

    parent = ParentModel(child=child1, children=[child2])

    assert parent.child.dt.tzinfo == UTC
    assert parent.children[0].dt.tzinfo == UTC
