"""`coerce_days` and the failure it exists to prevent.

`squaroff_config.days` is `integer[]`. Migration `20261003_02000` declared it `TEXT`, and on a text
column the write from `set_config` does not fail — PostgREST coerces the list to the string
`'[0,1,2,3,4]'`. The scheduler's only consumer is `current_dow not in days`, which raises
`TypeError` against a string, inside the loop's own `try`, whose handler abandons the whole batch.

So the assertion that matters is not "this parses". It is that a coerced row cannot take the
feature down with it.
"""

import pytest

from application.services.squareoff_service import DEFAULT_DAYS, coerce_days


class TestCoerceDays:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ([0, 1, 2, 3, 4], [0, 1, 2, 3, 4]),
            ([3], [3]),
            # what PostgREST actually wrote into the text column
            ("[0,1,2,3,4]", [0, 1, 2, 3, 4]),
            ("[0, 1, 2]", [0, 1, 2]),
            # the literal default the old migration shipped
            ("{1,2,3,4,5}", [1, 2, 3, 4, 5]),
            ("1,2,3", [1, 2, 3]),
            (" 6 ", [6]),
            ((0, 2), [0, 2]),
            (None, DEFAULT_DAYS),
            ("", DEFAULT_DAYS),
            ("   ", DEFAULT_DAYS),
            ("not a day list", DEFAULT_DAYS),
            (17, DEFAULT_DAYS),
        ],
    )
    def test_always_yields_a_list_of_ints(self, value, expected) -> None:
        assert coerce_days(value) == expected

    def test_honours_an_explicit_fallback(self) -> None:
        """A caller may pass its own default; `None` must not fall back to the module constant."""
        assert coerce_days(None, []) == []
        assert coerce_days("", []) == []
        assert coerce_days([1, 2, 3]) == [1, 2, 3]

    def test_never_returns_a_string(self) -> None:
        """The whole point. A string here is what makes `not in` raise."""
        for value in ("[0,1,2,3,4]", "{1,2,3,4,5}", "1,2,3", None, "", "junk"):
            assert isinstance(coerce_days(value), list)

    def test_a_coerced_row_cannot_stop_the_scheduler(self) -> None:
        """Reproduces the exact expression at squareoff_service.py:183.

        Measured on a real text column: the write succeeded and stored `'[0,1,2,3,4]'`, then this
        membership test raised `TypeError: 'in <string>' requires string as left operand, not int`,
        which the loop's handler logged and swallowed — abandoning every remaining user for that
        minute, and repeating every thirty seconds.
        """
        stored_in_a_text_column = "[0,1,2,3,4]"

        with pytest.raises(TypeError):
            0 not in stored_in_a_text_column  # what the loop used to evaluate

        days = coerce_days(stored_in_a_text_column)
        # Parenthesised deliberately: `0 not in days is False` would chain into a comparison
        # against `days` itself and quietly assert something else entirely.
        assert (0 not in days) is False   # Monday is configured, so it does not `continue`
        assert (5 not in days) is True    # and Saturday is genuinely excluded

    def test_exclusion_is_respected_not_coerced_away(self) -> None:
        """A user who configured Mon–Fri must not be squared off on the weekend.

        With the string form this check is the only thing standing between a weekend position and an
        automatic exit, so it is worth asserting the narrowed list is honoured exactly.
        """
        days = coerce_days("[0,1,2]")
        fires = [dow for dow in range(7) if dow not in days]
        assert fires == [3, 4, 5, 6]

    def test_default_is_the_weekday_range_the_rest_of_the_code_uses(self) -> None:
        assert DEFAULT_DAYS == [0, 1, 2, 3, 4]
        assert coerce_days(None) == DEFAULT_DAYS