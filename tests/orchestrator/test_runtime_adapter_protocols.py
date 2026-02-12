from __future__ import annotations

import unittest

from contracts.runtime_adapters import RuntimeRelayPolicy, RuntimeRetriever, RuntimeStateStore


class RuntimeAdapterProtocolTests(unittest.TestCase):
    def test_protocols_define_engine_agnostic_runtime_service_contracts(self) -> None:
        class _MemoryStateStore:
            def load_state(self) -> dict[str, object]:
                return {}

            def save_state(
                self,
                state: dict[str, object],
                *,
                node: str,
                from_status: str | None,
                to_status: str | None,
            ) -> dict[str, object]:
                return state

            def append_event(
                self,
                *,
                task_id: str,
                run_id: str,
                step_id: str | None,
                event_type: str,
                severity: str,
                payload: dict[str, object],
                dedup_key: str | None,
            ) -> None:
                return None

        class _Retriever:
            def retrieve(
                self,
                *,
                use_case: str,
                query: str,
                task_id: str | None,
                run_id: str | None,
                policy: object,
            ) -> dict[str, object]:
                return {"use_case": use_case, "query": query}

        class _RelayPolicy:
            def guard_action(self, *, action: str) -> None:
                return None

            def build_relay_payload(
                self,
                *,
                action: str,
                relay_context: dict[str, object],
                payload: dict[str, object],
            ) -> dict[str, object]:
                return {"action": action, "payload": payload, "relay_context": relay_context}

        self.assertIsInstance(_MemoryStateStore(), RuntimeStateStore)
        self.assertIsInstance(_Retriever(), RuntimeRetriever)
        self.assertIsInstance(_RelayPolicy(), RuntimeRelayPolicy)


if __name__ == "__main__":
    unittest.main()
