from __future__ import annotations

from datetime import timedelta
from typing import Any

from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from mcp import ClientSession
import mcp.types as types
from pydantic import TypeAdapter

from mcp.shared.session import ProgressFnT

from .models import AnalyzeResponse


class LowLatencyClientSession(ClientSession):
    """Schema-safe MCP client with all validators prepared before readiness.

    The upstream ClientSession.call_tool path invokes jsonschema.validate for
    every response. For this parser's advertised AnalyzeResponse schema, the
    authoritative Pydantic TypeAdapter is compiled once and reused. Unknown
    tools retain a compiled JSON Schema validator fallback.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._known_output_adapters: dict[str, TypeAdapter] = {
            "analyze_japanese": TypeAdapter(AnalyzeResponse),
        }
        self._pydantic_output_validators: dict[str, TypeAdapter] = {}
        self._jsonschema_output_validators: dict[str, Validator | None] = {}
        self._prepared_tools: set[str] = set()

    async def prepare_tools(self) -> types.ListToolsResult:
        """Fetch tool metadata and compile all output validators once."""
        result = await super().list_tools()
        for tool in result.tools:
            schema = tool.outputSchema
            adapter = self._known_output_adapters.get(tool.name)
            if adapter is not None:
                if schema != adapter.json_schema():
                    raise RuntimeError(
                        f"Advertised output schema for {tool.name} does not match "
                        "the authoritative response model"
                    )
                self._pydantic_output_validators[tool.name] = adapter
                self._jsonschema_output_validators.pop(tool.name, None)
                self._prepared_tools.add(tool.name)
                continue

            if schema is None:
                self._jsonschema_output_validators[tool.name] = None
            else:
                validator_class = validator_for(schema)
                validator_class.check_schema(schema)
                self._jsonschema_output_validators[tool.name] = validator_class(schema)
            self._prepared_tools.add(tool.name)
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
        """Call a tool and validate against its prepared output contract."""
        if name not in self._prepared_tools:
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
        if result.structuredContent is None:
            if name in self._pydantic_output_validators or self._jsonschema_output_validators.get(name) is not None:
                raise RuntimeError(
                    f"Tool {name} has an output schema but returned no structured content"
                )
            return result

        pydantic_validator = self._pydantic_output_validators.get(name)
        if pydantic_validator is not None:
            pydantic_validator.validate_python(result.structuredContent)
            return result

        jsonschema_validator = self._jsonschema_output_validators.get(name)
        if jsonschema_validator is not None:
            jsonschema_validator.validate(result.structuredContent)
        return result
