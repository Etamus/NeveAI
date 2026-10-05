import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from neveai.utils.middleware import (
    build_primary_web_search_query,
    should_run_web_search_for_message,
    chat_web_search_handler,
    is_unspecified_web_reference,
    is_web_model_discovery_follow_up,
    plan_chat_web_queries,
    compact_web_search_query,
)


class WebSearchContextTests(unittest.TestCase):
    def test_search_labels_preserve_sources_entities_and_negative_constraints(self):
        for query in [
            'Dado o cenario atual do Qwen, qual seria a melhor forma de comparar "Qwen3.5-0.8B" com outros modelos em geral?',
            'Given the current situation with models, what is the best way to compare https://huggingface.co/unsloth/Qwen3.5?',
            'Dado o cenario atual do aquecimento global, qual seria a melhor forma de ajudar o meio ambiente sem energia nuclear em geral?',
        ]:
            with self.subTest(query=query):
                result = compact_web_search_query(query)
                if 'https://' in query or '"' in query:
                    self.assertEqual(result, query)
                else:
                    self.assertIn('sem energia nuclear', result)

    def test_long_english_query_removes_only_conversational_framing(self):
        query = 'Given the current situation with global warming, what would be the best way to help protect the environment in general?'
        self.assertEqual(compact_web_search_query(query), 'global warming help protect the environment')

    def test_generic_best_model_questions_keep_the_actual_subject(self):
        url = "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF"
        root = f"Esse e o melhor modelo que tem atualmente da qwen? {url}"
        for question in ["Qual \u00e9 o melhor modelo?", "Qual o melhor modelo atualmente?", "Qual seria o melhor modelo?", "Qual modelo \u00e9 melhor?", "Quais s\u00e3o os melhores modelos?", "Qual \u00e9 o melhor modelo para programar?", "Qual \u00e9 o melhor?", "What is the best model?", "Which model is the best?", "What is the best model for coding?", "Which is the best model currently?", "Tem algum melhor?"]:
            with self.subTest(question=question):
                messages = [{"role": "user", "content": "Qual o melhor celular Samsung?"}, {"role": "user", "content": root}, {"role": "assistant", "content": "An unrelated iPhone or MacBook recommendation"}, {"role": "user", "content": question}]
                self.assertTrue(is_web_model_discovery_follow_up(question))
                query = build_primary_web_search_query(question, messages)
                self.assertIn("Qwen3.5", query)
                self.assertIn(url, query)
                self.assertNotIn("Samsung", query)
                self.assertNotIn("iPhone", query)

    def test_self_contained_price_question_is_not_blocked(self):
        self.assertFalse(is_unspecified_web_reference("Quanto custa o notebook Dell XPS 13?"))
        self.assertTrue(is_unspecified_web_reference("Quanto custa esse?"))
        self.assertTrue(is_unspecified_web_reference("Which one is better?"))

    def test_comparison_pronouns_keep_versions_and_source(self):
        root = "Qual a diferenca da versao v0.2.1 para v0.3 desse LoRA? https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo"
        for followup in ["Qual e melhor entre os dois?", "E qual tem mais qualidade?", "Qual voce recomenda deles?", "Which one is better?", "What about the first one?", "E ele funciona na AMD?"]:
            with self.subTest(followup=followup):
                query = build_primary_web_search_query(followup, [{"role": "user", "content": root}, {"role": "assistant", "content": "Unrelated politics"}, {"role": "user", "content": followup}])
                for term in ["Viggle", "v0.2.1", "v0.3"]:
                    self.assertIn(term, query)
                self.assertNotIn("politics", query)

    def test_long_root_keeps_supplied_url(self):
        url = "https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo"
        root = "Compare v0.2.1 and v0.3 " + "technical context " * 180 + url
        messages = [{"role": "user", "content": root}, {"role": "user", "content": "Qual e melhor entre os dois?"}]
        self.assertIn(url, build_primary_web_search_query(messages[-1]["content"], messages))

    def test_netflix_refinement_keeps_the_requested_title(self):
        messages = [
            {"role": "user", "content": "Existe chapinha pra barba?"},
            {"role": "assistant", "content": "Sim."},
            {"role": "user", "content": 'Do que se trata a serie "O Rato"?'},
            {"role": "assistant", "content": "Uma animacao do Globoplay."},
            {"role": "user", "content": "Me refiro a serie da netflix mais recente"},
        ]
        query = build_primary_web_search_query(messages[-1]["content"], messages)
        self.assertIn('"O Rato"', query)
        self.assertIn("netflix", query)
        self.assertNotIn("chapinha", query)
        self.assertNotIn("Globoplay", query)
        self.assertTrue(should_run_web_search_for_message(query))

    def test_independent_topic_does_not_inherit_previous_query(self):
        messages = [
            {"role": "user", "content": 'What is "O Rato"?'},
            {"role": "user", "content": "Qual a previsao do tempo hoje?"},
        ]
        query = build_primary_web_search_query(messages[-1]["content"], messages)
        self.assertEqual(query, "Qual a previsao do tempo hoje")

    def test_explicit_new_comparison_or_source_does_not_inherit_old_topic(self):
        for question in ["Qual melhor notebook para jogos?", "Which is better Samsung or Apple?", "Qual a diferenca desses modelos https://huggingface.co/team/new-model"]:
            messages = [{"role": "user", "content": "Lula versus Flavio"}, {"role": "user", "content": question}]
            self.assertNotIn("Lula", build_primary_web_search_query(question, messages))

    def test_multiple_refinements_keep_the_root_without_assistant_hallucinations(self):
        messages = [
            {"role": "user", "content": "Which ThinkPad T14 should I buy?"},
            {"role": "assistant", "content": "Buy an unrelated MacBook."},
            {"role": "user", "content": "What about the AMD version?"},
            {"role": "user", "content": "And in Brazil?"},
        ]
        query = build_primary_web_search_query(messages[-1]["content"], messages)
        for term in ("ThinkPad T14", "AMD", "Brazil"):
            self.assertIn(term, query)
        self.assertNotIn("MacBook", query)

    def test_multimodal_user_text_is_supported(self):
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Notebook Dell XPS 13"}]},
            {"role": "user", "content": "Quanto custa esse?"},
        ]
        self.assertIn("Dell XPS 13", build_primary_web_search_query(messages[-1]["content"], messages))

    def test_greetings_are_not_searched_but_factual_questions_are(self):
        self.assertFalse(should_run_web_search_for_message("Bom dia!"))
        self.assertFalse(should_run_web_search_for_message("Obrigado!"))
        self.assertTrue(should_run_web_search_for_message("Existe chapinha pra barba?"))
        self.assertTrue(should_run_web_search_for_message('Do que se trata a serie "O Rato"?'))

    def test_follow_up_without_history_has_a_safe_fallback(self):
        self.assertEqual(build_primary_web_search_query("Me refiro a Netflix"), "Me refiro a Netflix")

    def test_acknowledgements_do_not_replace_the_topic(self):
        messages = [
            {"role": "user", "content": "Notebook Dell XPS 13"},
            {"role": "user", "content": "Obrigado!"},
            {"role": "user", "content": "Quanto custa esse?"},
        ]
        query = build_primary_web_search_query(messages[-1]["content"], messages)
        self.assertIn("Dell XPS 13", query)
        self.assertNotIn("Obrigado", query)


class WebSearchHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_verbose_request_uses_the_existing_planner_and_preserves_its_subject(self):
        question = 'Eu gostaria de entender quais medidas de mitigacao do aquecimento global sao mais eficazes para uma pessoa comum aplicar em sua rotina diaria'
        form = {'model': 'local', 'messages': [{'role': 'user', 'content': question}]}
        with patch('neveai.utils.middleware.generate_chat_completion', AsyncMock(return_value={'choices': [{'message': {'content': '{"queries": ["aquecimento global medidas mitigacao individual eficazes"]}'}}]})) as model:
            result = await plan_chat_web_queries(SimpleNamespace(app=SimpleNamespace()), form, None, question)
        self.assertEqual(result, ['aquecimento global medidas mitigacao individual eficazes'])
        model.assert_awaited_once()

    async def test_long_question_becomes_concise_without_an_extra_model_call(self):
        question = 'Dado o cenario atual do aquecimento global, qual seria a melhor forma de ajudar o meio ambiente em geral?'
        form = {'model': 'local', 'messages': [{'role': 'user', 'content': question}]}
        with patch('neveai.utils.middleware.generate_chat_completion', AsyncMock()) as model:
            queries = await plan_chat_web_queries(SimpleNamespace(app=SimpleNamespace()), form, None, question)
        self.assertEqual(queries, ['aquecimento global ajudar o meio ambiente'])
        model.assert_not_awaited()

    async def test_planner_rejects_invented_years_variants_and_changed_subject(self):
        root = "Melhor modelo Qwen https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF"
        form = {"model": "local", "messages": [{"role": "user", "content": root}, {"role": "user", "content": "Qual e o melhor modelo?"}]}
        for query in ["best Qwen models 2024", "Qwen3.5-7B vs Qwen3.5-14B", "best iPhone models"]:
            with self.subTest(query=query), patch("neveai.utils.middleware.generate_chat_completion", AsyncMock(return_value={"choices": [{"message": {"content": json.dumps({"queries": [query]})}}]})):
                result = await plan_chat_web_queries(SimpleNamespace(app=SimpleNamespace()), form, None, root)
                self.assertEqual(result, [root])

    async def test_planner_accepts_family_discovery_without_inventing_a_release(self):
        root = "Melhor modelo Qwen https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF"
        form = {"model": "local", "messages": [{"role": "user", "content": root}, {"role": "user", "content": "Qual e o melhor modelo?"}]}
        query = "best Qwen language models for coding"
        with patch("neveai.utils.middleware.generate_chat_completion", AsyncMock(return_value={"choices": [{"message": {"content": '{"queries": ["best Qwen language models for coding"]}'}}]})):
            result = await plan_chat_web_queries(SimpleNamespace(app=SimpleNamespace()), form, None, root)
        self.assertEqual(result, [query])

    async def test_best_model_followup_reads_source_and_searches_for_alternatives(self):
        url = "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF"
        form = {"model": "local", "messages": [{"role": "user", "content": f"Esse e o melhor modelo da qwen? {url}"}, {"role": "user", "content": "Qual \u00e9 o melhor modelo?"}]}
        with patch("neveai.utils.middleware.process_web_search", AsyncMock(return_value={"status": False})) as search:
            await chat_web_search_handler(SimpleNamespace(state=SimpleNamespace()), form, {"__event_emitter__": AsyncMock()}, None)
        search_form = search.call_args.args[1]
        self.assertEqual(search_form.urls, [url])
        self.assertTrue(search_form.search_after_urls)
        self.assertIn("Qwen", search_form.queries[0])

    async def test_comparison_reuses_source_instead_of_searching_pronouns(self):
        url = "https://huggingface.co/Viggle/Qwen-Image-2.1-viggle-turbo"
        form = {"model": "local", "messages": [{"role": "user", "content": f"Compare v0.2.1 and v0.3 {url}"}, {"role": "user", "content": "Qual e melhor entre os dois?"}]}
        with patch("neveai.utils.middleware.process_web_search", AsyncMock(return_value={"status": False})) as search, patch("neveai.utils.middleware.plan_chat_web_queries", AsyncMock()) as planner:
            await chat_web_search_handler(SimpleNamespace(state=SimpleNamespace()), form, {"__event_emitter__": AsyncMock()}, None)
        self.assertEqual(search.call_args.args[1].urls, [url])
        self.assertIn("v0.2.1", search.call_args.args[1].question)
        planner.assert_not_awaited()

    async def test_unresolved_comparison_asks_instead_of_searching_unrelated_topics(self):
        form = {"model": "local", "messages": [{"role": "user", "content": "Qual e melhor entre os dois?"}]}
        with patch("neveai.utils.middleware.process_web_search", AsyncMock()) as search:
            result = await chat_web_search_handler(SimpleNamespace(state=SimpleNamespace()), form, {"__event_emitter__": AsyncMock()}, None)
        search.assert_not_awaited()
        self.assertIn("Ask the user", result["messages"][0]["content"])

    async def test_follow_up_query_reaches_search_and_keeps_original_messages(self):
        messages = [
            {"role": "user", "content": 'Do que se trata a serie "O Rato"?'},
            {"role": "assistant", "content": "Uma animacao do Globoplay."},
            {"role": "user", "content": "Me refiro a serie da netflix mais recente"},
        ]
        form = {"messages": messages, "model": "test-local"}
        emitter = AsyncMock()
        search = AsyncMock(return_value={"status": False})
        with patch("neveai.utils.middleware.process_web_search", search), patch(
            "neveai.utils.middleware.generate_queries", AsyncMock()
        ) as generate:
            result = await chat_web_search_handler(
                SimpleNamespace(state=SimpleNamespace()), form,
                {"__event_emitter__": emitter, "__features__": {}}, None,
            )
        query = search.call_args.args[1].queries[0]
        self.assertIn('"O Rato"', query)
        self.assertIn("netflix", query)
        self.assertNotIn("Globoplay", query)
        self.assertEqual(result["messages"][-len(messages):], messages)
        self.assertIn("no usable evidence", result["messages"][0]["content"])
        generate.assert_not_awaited()
        self.assertTrue(emitter.call_args.args[0]["data"]["done"])


if __name__ == "__main__":
    unittest.main()
