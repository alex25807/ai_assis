from bot.knowledge import company_text, faq_text, system_prompt


def test_knowledge_matches_site_facts() -> None:
    company = company_text()
    assert "Бабушкина" in company
    assert "Gealan" in company
    assert "Часы: 10:00–18:00" in company
    assert "Не говорить, что работаем с 9:00" in company
    assert "TBD" in faq_text()
    prompt = system_prompt()
    assert "не выдумывай цены" in prompt.lower() or "Не выдумывай цены" in prompt
    assert "Savvy" in prompt or "Savvy" in company
