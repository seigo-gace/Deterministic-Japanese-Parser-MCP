from __future__ import annotations

from datetime import timedelta
from typing import Any

from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from mcp import ClientSession
import mcp.types as types

from mcp.shared.session import ProgressFnT


class LowLatencyClientSession(ClientSession):
    """MCP ClientSession with output schemas compiled once at readiness.

    The upstream ClientSession.call_tool path invokes jsonschema.validate for
    every response. That API checks and recompiles the complete output schema on
    each call. This subclass preserves the same response-schema validation but
    prepares one validator per tool before the session is considered ready.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._compiled_output_validators: dict[str, Validator | None] = {}

    async def prepare_tools(self) -> types.ListToolsResult:
        """Fetch tool metadata and compile all output validators once."""
        result = await super().list_tools()
        for tool in result.tools:
            schema = tool.outputSchema
            if schema is None:
                self._compiled_output_validators[tool.name] = None
                continue
            validator_class = validator_for(schema)
            validator_class.check_schema(schema)
            self._compiled_output_validators[tool.name] = validator_class(schema)
        return result

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
        progress_callback: ProgressFnT | None = None,
        *,
        meta: dict[str, Any] | None = None,
    ) -> types.CallToolResult:
        """Call a tool and validate against the precompiled output schema."""
        if name not in self._compiled_output_validators:
            await self.prepare_tools()

        request_meta: types.RequestParams.Meta | None = None
        if meta is not None:
            request_meta = types.RequestParams.Meta(**meta)

        result = await self.send_request(
            types.ClientRequest(
                types.CallToolRequest(
                    params=types.CallToolRequestParams(
                        name=name,
                        arguments=arguments,
                        _meta=request_meta,
                    )
                )
            ),
            types.CallToolResult,
            request_read_timeout_seconds=read_timeout_seconds,
            progress_callback=progress_callback,
        )

        if result.isError:
            return result

        validator = self._compiled_output_validators.get(name)
        if validator is not None:
            if result.structuredContent is None:
                raise RuntimeError(
                    f"Tool {name} has an output schema but returned no structured content"
                )
            validator.validate(result.structuredContent)
        return result
