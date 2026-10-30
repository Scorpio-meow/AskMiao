import pytest
from app.services.openapi_parser import OpenApiParser
@pytest.mark.anyio
async def test_openapi_parser():
    oas2_yaml = """
swagger: '2.0'
info:
  title: Petstore 2.0
  version: 1.0.0
host: petstore.swagger.io
basePath: /v2
schemes:
  - https
paths:
  /pet/{petId}:
    get:
      summary: Find pet by ID
      operationId: getPetById
      parameters:
        - name: petId
          in: path
          required: true
          type: integer
      responses:
        200:
          description: OK
"""
    res2 = await OpenApiParser.parse(oas2_yaml)
    assert res2["version"] == "swagger_2.0"
    assert res2["base_url"] == "https://petstore.swagger.io/v2"
    assert len(res2["endpoints"]) == 1
    assert res2["endpoints"][0]["name"] == "getpetbyid"
    assert "petId" in res2["endpoints"][0]["parameters_schema"]["properties"]
    print("OAS 2.0 測試通過: version =", res2["version"], ", endpoints =", len(res2["endpoints"]))
    oas3_yaml = """
openapi: 3.0.3
info:
  title: User API 3.0
  version: 1.0.0
servers:
  - url: https://api.example.com/v3
paths:
  /users:
    post:
      summary: Create new user
      operationId: createUser
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                username:
                  type: string
                email:
                  type: string
              required:
                - username
"""
    res3 = await OpenApiParser.parse(oas3_yaml)
    assert res3["version"] == "openapi_3.0"
    assert res3["base_url"] == "https://api.example.com/v3"
    assert len(res3["endpoints"]) == 1
    assert "username" in res3["endpoints"][0]["parameters_schema"]["properties"]
    print("OAS 3.0 測試通過: version =", res3["version"], ", properties =", list(res3["endpoints"][0]["parameters_schema"]["properties"].keys()))
    oas31_yaml = """
openapi: 3.1.0
info:
  title: Webhook API 3.1
  version: 2.0.0
servers:
  - url: https://api.v31.com
paths:
  /items/{itemId}:
    put:
      summary: Update Item
      operationId: updateItem
      parameters:
        - name: itemId
          in: path
          required: true
          schema:
            type:
              - string
              - integer
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                price:
                  type:
                    - number
                    - 'null'
"""
    res31 = await OpenApiParser.parse(oas31_yaml)
    assert res31["version"] == "openapi_3.1"
    assert res31["base_url"] == "https://api.v31.com"
    assert len(res31["endpoints"]) == 1
    print("OAS 3.1 測試通過: version =", res31["version"], ", endpoints =", len(res31["endpoints"]))
    print("All OpenAPI Parser tests passed successfully!")
if __name__ == "__main__":
    asyncio.run(main())

@pytest.mark.anyio
async def test_yaml_aliases_are_rejected():
    from app.core.error_response import SafeClientError

    spec_with_alias = """
openapi: 3.0.3
info: &info
  title: Alias API
  version: 1.0.0
x-copy: *info
paths: {}
"""
    with pytest.raises(SafeClientError, match="別名"):
        await OpenApiParser.parse(spec_with_alias)
    # 只有錨點、沒有別名的規格照常解析，回應不再夾帶整份原始規格
    parsed = await OpenApiParser.parse(spec_with_alias.replace("x-copy: *info\n", ""))
    assert parsed["title"] == "Alias API"
    assert "raw_spec" not in parsed


def test_long_operation_id_becomes_a_valid_stable_function_name():
    import re
    from app.core.limits import MAX_TOOL_NAME_CHARS

    long_id = "listAllTheOrganizationRepositoryWebhookDeliveriesForTheGivenHookIdentifier"
    name = OpenApiParser._generate_tool_name("get", "/hooks", long_id)
    assert re.fullmatch(rf"[a-zA-Z0-9_-]{{1,{MAX_TOOL_NAME_CHARS}}}", name)
    assert name == OpenApiParser._generate_tool_name("get", "/hooks", long_id)
    assert name != OpenApiParser._generate_tool_name("get", "/hooks", long_id + "V2")
    assert OpenApiParser._generate_tool_name("get", "/hooks", "listHooks") == "listhooks"


@pytest.mark.anyio
async def test_reused_ref_keeps_its_fields_in_every_branch():
    import json
    from app.core.limits import MAX_OPENAPI_SCHEMA_REFS

    depth = 20
    schemas = {
        "Loc": {"type": "object", "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}}},
        "Trip": {"type": "object", "properties": {
            "origin": {"$ref": "#/components/schemas/Loc"}, "destination": {"$ref": "#/components/schemas/Loc"},
        }},
        "Node": {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/Node"}}},
        **{f"L{i}": {"type": "object", "properties": {
            "a": {"$ref": f"#/components/schemas/L{i + 1}"}, "b": {"$ref": f"#/components/schemas/L{i + 1}"},
        }} for i in range(depth)},
        f"L{depth}": {"type": "string"},
    }
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "components": {"schemas": schemas},
        "paths": {"/trips": {"post": {"operationId": "createTrip", "requestBody": {"content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Trip"}},
        }}}}},
    }
    properties = (await OpenApiParser.parse(json.dumps(spec)))["endpoints"][0]["parameters_schema"]["properties"]
    loc = {"lat": {"type": "number"}, "lng": {"type": "number"}}
    assert properties["origin"]["properties"] == loc
    assert properties["destination"]["properties"] == loc
    node = OpenApiParser._clean_schema({"$ref": "#/components/schemas/Node"}, spec)
    assert "properties" not in node["properties"]["child"]
    fan_out = OpenApiParser._clean_schema({"$ref": "#/components/schemas/L0"}, spec)
    assert json.dumps(fan_out).count('"properties"') <= MAX_OPENAPI_SCHEMA_REFS


@pytest.mark.anyio
async def test_referenced_parameters_bodies_and_security_schemes_keep_their_fields():
    import json

    spec = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "servers": [{"url": "https://api.example.com"}],
        "security": [{"Key": []}],
        "components": {
            "schemas": {"Pet": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
            "parameters": {
                "PetId": {"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}},
                "Limit": {"$ref": "#/components/parameters/RealLimit"},
                "RealLimit": {"name": "limit", "in": "query", "schema": {"type": "integer"}},
            },
            "requestBodies": {"Pet": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}}},
            "securitySchemes": {
                "Key": {"$ref": "#/components/securitySchemes/RealKey"},
                "RealKey": {"type": "apiKey", "in": "header", "name": "X-Key"},
            },
        },
        "paths": {"/pets/{petId}": {"put": {
            "operationId": "updatePet",
            "parameters": [{"$ref": "#/components/parameters/PetId"}, {"$ref": "#/components/parameters/Limit"}],
            "requestBody": {"$ref": "#/components/requestBodies/Pet"},
        }}},
    }
    endpoint = (await OpenApiParser.parse(json.dumps(spec)))["endpoints"][0]
    assert endpoint["param_locations"] == {"petId": "path", "limit": "query", "name": "body"}
    assert endpoint["parameters_schema"]["properties"] == {
        "petId": {"type": "integer"}, "limit": {"type": "integer"}, "name": {"type": "string"},
    }
    assert set(endpoint["parameters_schema"]["required"]) == {"petId", "name"}
    assert endpoint["auth_type"] == "api_key"
    assert endpoint["auth_config"]["key_name"] == "X-Key"
