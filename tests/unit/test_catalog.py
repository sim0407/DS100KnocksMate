"""core/exercises/catalog.py: 問題カタログと採点定義（TOML）の読み込み。"""

import pytest

from core.exercises import catalog
from core.grading.compare import SortKey, TableSpec


@pytest.fixture(scope="module")
def exercises():
    return catalog.load_exercises()


def test_all_100_exercises_in_order(exercises):
    assert [e.id for e in exercises] == [f"{i:03d}" for i in range(1, 101)]


def test_statements_are_language_specific(exercises):
    e = exercises[0]
    assert "df_receipt" in e.statements["python"]
    assert "（receipt）" in e.statements["sql"]


def test_verified_spec_is_loaded(exercises):
    spec = exercises[0].grading["python"]
    assert spec.strategy == "table"
    assert spec.reference == "df_receipt"
    assert spec.table == TableSpec(rows="subset_n", n=10)
    assert exercises[0].status == "verified"


def test_exercise_without_spec_is_manual_review(exercises):
    e = next(e for e in exercises if e.id == "100")
    assert e.status == "unsupported"
    for lang in catalog.LANGUAGES:
        assert e.grading[lang].strategy == "manual_review"
        assert "未対応" in e.grading[lang].reason


def test_dependencies_are_exposed(exercises):
    assert next(e for e in exercises if e.id == "044").depends_on == ("043",)


def test_title_is_short_first_line(exercises):
    title = exercises[0].title("python")
    assert title.startswith("レシート明細データ")
    assert len(title) <= 41


def test_lookup_by_id():
    assert catalog.get_exercise("003").id == "003"
    with pytest.raises(KeyError):
        catalog.get_exercise("999")


def test_answers_are_loaded_separately():
    answers = catalog.load_answers()
    assert answers["001"]["python"] == ["df_receipt.head(10)"]


# ---------------------------------------------------------------- 採点定義の検証


def parse(text, expected_id="001"):
    import tomllib

    return catalog.parse_spec(tomllib.loads(text), expected_id)


def test_parse_sort_keys_and_options():
    status, grading = parse(
        """
id = "001"
status = "draft"
[python]
strategy = "table"
rows = "top_n"
n = 5
reference = "x"
column_order = false
float_decimals = 3
sort_keys = [{ column = "amount", descending = true }, { column = "id" }]
[sql]
strategy = "manual_review"
reason = "乱数のため"
"""
    )
    assert status == "draft"
    assert grading["python"].table == TableSpec(
        rows="top_n",
        n=5,
        sort_keys=(SortKey("amount", True), SortKey("id")),
        column_order=False,
        float_decimals=3,
    )
    assert grading["sql"].strategy == "manual_review"
    assert grading["sql"].reason == "乱数のため"


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ('id = "002"\nstatus = "verified"', "id"),
        ('id = "001"\nstatus = "done"', "status"),
        ('id = "001"\nstatus = "verified"\n[python]\nstrategy = "magic"', "strategy"),
        (
            'id = "001"\nstatus = "verified"\n[python]\nstrategy = "table"\nrows = "unordered"',
            "reference",
        ),
        (
            'id = "001"\nstatus = "verified"\n[python]\nstrategy = "table"\nrows = "subset_n"\nreference = "x"',
            "n",
        ),
        (
            'id = "001"\nstatus = "verified"\n[python]\nstrategy = "table"\nrows = "sideways"\nreference = "x"',
            "rows",
        ),
        ('id = "001"\nstatus = "verified"\n[ruby]\nstrategy = "table"', "ruby"),
        (
            'id = "001"\nstatus = "verified"\n[python]\nstrategy = "table"\nreference = "x"\ntypo = 1',
            "typo",
        ),
    ],
)
def test_parse_spec_rejects_invalid(text, match):
    with pytest.raises(ValueError, match=match):
        parse(text)


def test_every_spec_file_is_valid_and_matches_a_problem(exercises):
    ids = {e.id for e in exercises}
    files = sorted(catalog.PROBLEMS_DIR.glob("*.toml"))
    assert files, "採点定義ファイルがない"
    for path in files:
        assert path.stem in ids


def test_parse_column_names_and_note():
    _, grading = parse(
        """
id = "001"
status = "verified"
[sql]
strategy = "table"
reference = "SELECT 1"
column_names = false
note = "列名は問いません"
[python]
strategy = "scalar"
reference = "1"
note = "値だけを判定します"
"""
    )
    assert grading["sql"].table.column_names is False
    assert grading["sql"].note == "列名は問いません"
    assert grading["python"].note == "値だけを判定します"


def test_manual_review_spec_requires_reason():
    with pytest.raises(ValueError, match="reason"):
        parse('id = "001"\nstatus = "verified"\n[python]\nstrategy = "manual_review"')
