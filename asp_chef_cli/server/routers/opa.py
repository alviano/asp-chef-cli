from fastapi import APIRouter
import json as json_module
from asp_chef_cli.server.dependencies import endpoint
from opa import OPAClient

router = APIRouter()

client = OPAClient()


@endpoint(router, "/opa-eval/")
async def evaluate_opa_policy(json):
    policy = json["policy"]
    policy_name = json["policy_name"]
    input_file_uuid = json["uuid"]
    input_data = json_module.loads(json["json"])
    input_key = json.get("key")
    should_return_allowed = json.get("allow", True)

    opa_input = [item[input_key] for item in input_data] if input_key else input_data

    client.save_document(input_file_uuid, opa_input)
    client.save_policy("policy", policy)
    opa_result = client.check_policy(
        f"policy.{policy_name}", input=opa_input, pretty=True
    )

    if not should_return_allowed:
        allowed_keys = {
            (item["user"], item["method"], item["action"]) for item in opa_result
        }

        final_result = [
            {
                "user": item["user"]["name"],
                "method": item["request"]["method"],
                "action": item["request"]["path"],
                "allow": False,
            }
            for item in opa_input
            if (
                item["user"]["name"],
                item["request"]["method"],
                item["request"]["path"],
            )
            not in allowed_keys
        ]

    else:
        final_result = opa_result

    if input_key:
        result_lookup_keys = {
            (item["user"], item["method"], item["action"]) for item in final_result
        }

        final_result = [
            original_item
            for original_item in input_data
            if (
                original_item[input_key]["user"]["name"],
                original_item[input_key]["request"]["method"],
                original_item[input_key]["request"]["path"],
            )
            in result_lookup_keys
        ]

    return {"result": str(final_result)}
