from takopi.telegram.loop import _forum_topic_title_context


class _Runtime:
    def __init__(self, aliases: tuple[str, ...]) -> None:
        self._aliases = aliases

    def project_aliases(self) -> tuple[str, ...]:
        return self._aliases

    def normalize_project_key(self, value: str) -> str | None:
        lookup = {alias.lower(): alias.lower() for alias in self._aliases}
        return lookup.get(value.lower())


def test_forum_topic_title_context_matches_delegate_skill_suffix() -> None:
    ctx = _forum_topic_title_context(
        _Runtime(("kimi_delegate",)), "Kimi delegate skill"
    )

    assert ctx is not None
    assert ctx.project == "kimi_delegate"
    assert ctx.branch == "main"


def test_forum_topic_title_context_uses_explicit_branch() -> None:
    ctx = _forum_topic_title_context(
        _Runtime(("devin_delegate",)), "devin_delegate @feat"
    )

    assert ctx is not None
    assert ctx.project == "devin_delegate"
    assert ctx.branch == "feat"


def test_forum_topic_title_context_ignores_unknown_title() -> None:
    assert (
        _forum_topic_title_context(_Runtime(("kimi_delegate",)), "random chat") is None
    )
