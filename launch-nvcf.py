import json
import os
import yaml
import requests
from requests.exceptions import HTTPError
from jinja2 import Environment, FileSystemLoader
import time
import sys
from dataclasses import dataclass
import argparse
from types import SimpleNamespace
import logging

from common import BaseClass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("nvcf")


@dataclass
class NVCFRunner(BaseClass):
    job_name: str
    env_vars: dict
    backend: str
    function_name: str = None
    environment: str = "test"
    debug_mode: bool = False

    def __post_init__(self):
        # Initialize the base class
        super().__init__()
        self.deployment_successful = False
        self.functions_objects = []
        self.function_updates = []
        self.function_creates = []
        self.load_environment_variables()
        logger.info("Starting NVCF Launcher")
        logger.info(f"job_name: {self.job_name}")

    def _conf_nvcf(self, nvcf_type, method="POST", payload=None, url=None):
        if url is None:
            url = self.SCOPE_API_MAP[nvcf_type]
        logger.info(f"{self.job_name}: {method} - Configuring NVCF {nvcf_type}.")
        logger.info(f"{self.job_name}: {method} - {url}")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.nvcf_api_key}"}

        try:
            if method.upper() == "POST":
                logger.debug(f"Sending POST request to {url} with payload: {json.dumps(payload, indent=4)}")
                response = requests.post(url, headers=headers, json=payload, timeout=30)
            elif method.upper() == "DELETE":
                logger.debug(f"Sending DELETE request to {url} with payload: {json.dumps(payload, indent=4)}")
                response = requests.delete(url, headers=headers, json=payload, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            logger.debug(f"Response status code: {response.status_code}")
            logger.debug(f"Response headers: {response.headers}")
            logger.debug(f"Response content: {response.content}")

            # Check if the response was a redirect
            if response.status_code in (301, 302):
                logger.warning(f"Request was redirected to {response.headers.get('Location')}")

            response.raise_for_status()

            if response.status_code == 204:
                logger.info(
                    f"{self.job_name}: {method} - Successfully processed NVCF {nvcf_type}. No content in response."
                )
                return None

            # Check if the content type is JSON before attempting to parse
            if 'application/json' in response.headers.get('Content-Type', ''):
                result = response.json()
                result_obj = self._convert_dict_to_object(result)
                logger.info(f"{self.job_name}: {method} - Successfully processed NVCF {nvcf_type}.")
                return result_obj
            else:
                logger.error(f"Unexpected content type: {response.headers.get('Content-Type')}")
                logger.error(f"Response content: {response.text}")
                raise Exception("Unexpected content type")

        except HTTPError as http_err:
            logger.error(
                f"Failed request details: URL: {url}, Payload: {json.dumps(payload, indent=4)}, Headers: {headers}"
            )
            logger.error(f"{self.job_name}: HTTP error occurred: {http_err}")
            logger.error(f"Response Body: {response.text if response.text else 'No msg body.'}")
            if http_err.response.status_code == 401:
                logger.info(f"{self.job_name}: 401 encountered - re-authenticating")
                self._user_authentication_nvcf()
            else:
                raise Exception(f"HTTP error occurred: {http_err}")

        except (requests.Timeout, ConnectionError) as err:
            logger.error(f"{self.job_name}: Failed to process NVCF {nvcf_type} with {method} request - {repr(err)}")
            raise Exception(f"Unreachable, please try again later: {err}")

    def _poll_nvcf(
        self, nvcf_type, success_check, method="get", payload=None, timeout=86400, interval=30, op="deploy", url=None
    ):
        if url is None:
            url = self.SCOPE_API_MAP[nvcf_type]
        timeout = float(timeout)
        interval = float(interval)
        start_time = time.time()
        log_payload = {"requestBody": {"check": "log"}}
        previous_log_content = ""
        success = False

        try:
            while time.time() - start_time < timeout:
                try:
                    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.nvcf_api_key}"}
                    if method == "get":
                        response = requests.get(url, headers=headers)
                    elif method == "post":
                        response = requests.post(url, headers=headers, json=payload)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    logger.debug(f"Response status code: {response.status_code}")
                    logger.debug(f"Response headers: {response.headers}")
                    logger.debug(f"Response content: {response.content}")

                    response.raise_for_status()

                    if 'application/json' in response.headers.get('Content-Type', ''):
                        data = response.json()
                    else:
                        logger.error(f"Unexpected content type: {response.headers.get('Content-Type')}")
                        logger.error(f"Response content: {response.text}")
                        raise Exception("Unexpected content type")

                    logger.info(f"{self.job_name}: Waiting for NVCF function {op}")

                    if payload and payload.get("requestBody", {}).get("check") == "status":
                        log_response = requests.post(url, headers=headers, json=log_payload)
                        log_response.raise_for_status()
                        log_data = log_response.json()
                        current_log_content = log_data.get("response", {}).get("log", "")

                        if isinstance(current_log_content, str):
                            new_log_content = current_log_content.replace(previous_log_content, "")
                            if new_log_content.strip():
                                logger.info(f"\n{new_log_content}")
                            previous_log_content = current_log_content

                    if success_check(data):
                        success = True
                        elapsed_time = time.time() - start_time
                        logger.info(
                            f"{self.job_name}: NVCF function met {op} success condition in"
                            f" {elapsed_time:.2f} seconds."
                        )
                        return data

                    time.sleep(interval)

                except requests.HTTPError as http_err:
                    logger.error(f"{self.job_name}: HTTP error occurred: {http_err}")
                    logger.error(f"Response Body: {response.text if response.text else 'No msg body.'}")
                    if http_err.response.status_code == 401:
                        logger.info(f"{self.job_name}: 401 encountered - re-authenticating")
                        self._user_authentication_nvcf(logger=logger)
                        continue
                    else:
                        raise Exception(f"HTTP error occurred: {http_err}")

                except (ConnectionError, ValueError) as err:
                    raise Exception(f"Error while handling request: {err}")

        finally:
            if not success:
                if op == "deploy":
                    self.deployment_successful = False
                raise TimeoutError(
                    f"{self.job_name}: NVCF function did not meet success condition within"
                    f" {int(time.time() - start_time)} seconds"
                )

    def categorize_functions(self):
        self.function_updates = []
        self.function_creates = []

        if not self.functions_objects:
            logger.error("functions_objects is None or empty.")

        if not hasattr(self, "manifest") or not hasattr(self, "functions_objects"):
            logger.error("Manifest or functions_objects not initialized")
            return

        if getattr(self.manifest, "manual_deploy", False):
            logger.info("Manual deploy nvcf-conf flag is set to true, skipping processing of creating NVCF")
            exit(0)

        # Filter functions based on the type matching the environment
        relevant_functions = [fn for fn in self.manifest.functions if fn.type == self.environment]

        for fn in relevant_functions:
            fn_key = f"{'qa' if fn.type == 'test-' else ''}{self.manifest.name}"
            manifest_alias = getattr(self.manifest, "function_alias", None)

            # Collect all matching functions
            matching_functions = [
                f
                for f in self.functions_objects
                if (
                    (
                        f.name == fn_key
                        or f.name == self.manifest.name
                        or (manifest_alias and f.name == manifest_alias)
                        or (manifest_alias and f.name == f"{'qa' if fn.type == 'test' else 'ai'}-{manifest_alias}")
                    )
                    and (f.status == "ACTIVE" or f.status == "ERROR" or f.status == "INACTIVE")
                )
            ]
            logger.info(f"Function version(s) match: {[func.versionId for func in matching_functions]}")

            if matching_functions:
                # Copy properties from the latest matching function to fn
                latest_fn = max(matching_functions, key=lambda x: x.versionId)
                fn.name = self.manifest.name
                fn.current_id = getattr(latest_fn, "id", None)
                fn.current_version_id = getattr(latest_fn, "versionId", None)
                fn.current_status = getattr(latest_fn, "status", None)
                # Store all matching functions for potential deletion
                fn.old_versions = [func.versionId for func in matching_functions]
                self.function_updates.append(fn)
            else:
                fn.name = self.manifest.name
                self.function_creates.append(fn)

        logger.info(f"Functions to update: {[func.name+' (ID: '+func.current_id+')' for func in self.function_updates]}")
        logger.info(f"Functions to create: {[func.name for func in self.function_creates]}")

        if bool(fn.auto_clean):
            logger.info(f"Function version(s) to delete: {[func.versionId for func in matching_functions]}")

    def _reconcile(self, fn_list, op="create"):
        for fn in fn_list:
            if fn is None:
                logger.error("Encountered a None function in the list.")
                continue
            nvcf_fr_payload = {
                "name": f"{'qa' if fn.type == 'test' else 'ai'}-{fn.name}",
                "inferenceUrl": fn.inferenceUrl,
                "inferencePort": fn.inferencePort,
                "healthUri": fn.healthUri,
                "containerImage": f"{ fn.containerImage if 'nvcr.io' in fn.containerImage else '/'.join(['nvcr.io',{fn.ngc_org},{fn.ngc_team},{fn.containerImage}])}",
                "apiBodyFormat": fn.apiBodyFormat,
            }

            if getattr(fn, "containerEnvironment", None):
                nvcf_fr_payload["containerEnvironment"] = [
                    {"key": c.key, "value": c.value} for c in fn.containerEnvironment
                ]

            container_args = getattr(fn, "containerArgs", None)
            if container_args is not None:
                nvcf_fr_payload["containerArgs"] = container_args

            ### WIP
            helm_chart = getattr(fn, "helmChart", None)
            if helm_chart:
                nvcf_fr_payload["helmChart"] = helm_chart

            helm_chart_service_name = getattr(fn, "helmChartServiceName", None)
            if helm_chart_service_name:
                nvcf_fr_payload["helmChartServiceName"] = helm_chart

            resources = getattr(fn, "resources", [])
            if getattr(fn, "resources", []):
                nvcf_fr_payload["resources"] = resources

            if getattr(fn, "models", None):
                nvcf_fr_payload["models"] = [
                    {
                        "name": m.name,
                        "version": f"{m.version}",
                        "uri": f"/v2/org/{fn.ngc_org}/team/{fn.ngc_team}/models/{m.uri}/{m.version}/files",
                    }
                    for m in fn.models
                ]

            nvcf_fd_payload = {
                "deploymentSpecifications": [
                    {
                        "gpu": fn.inst_gpu_type,
                        "instanceType": fn.inst_type,
                        "backend": fn.inst_backend,
                        "maxInstances": fn.inst_max,
                        "minInstances": fn.inst_min,
                        "maxRequestConcurrency": getattr(fn, "inst_max_request_concurrency", 1),
                    }
                ]
            }

            # In debug mode, print the payloads and skip the API calls
            if self.debug_mode:
                logger.info("nvcf_fr_payload: " + json.dumps(nvcf_fr_payload, indent=4))
                logger.info("nvcf_fd_payload: " + json.dumps(nvcf_fd_payload, indent=4))
                continue  # Skip to the next iteration

            if op == "create":
                o_url = f"{self.SCOPE_API_MAP['register_function']}/functions"
            elif op == "update":
                o_url = f"{self.SCOPE_API_MAP['update_function']}/functions/{fn.current_id}/versions"

            nvcf_fn = self._conf_nvcf(
                nvcf_type="function", method="POST", payload=nvcf_fr_payload, url=o_url
            )

            self.nvcf_fn_reg_url = f"{self.SCOPE_API_MAP['update_function']}/functions/{nvcf_fn.function.id}/versions/{nvcf_fn.function.versionId}"
            self.nvcf_fn_deploy_url = (
                    f"{self.SCOPE_API_MAP['deploy_function']}/deployments/functions/{nvcf_fn.function.id}/versions/{nvcf_fn.function.versionId}"
                )
            logger.info(f"{self.job_name}: Initializing deployment for: {self.nvcf_fn_deploy_url}")

            time.sleep(2)
            self._conf_nvcf(
                nvcf_type="deploy_function",
                method="POST",
                payload=nvcf_fd_payload,
                url=self.nvcf_fn_deploy_url
            )

            self._poll_nvcf(
                nvcf_type="deploy_function",
                success_check=lambda data: data.get("deployment", {}).get("functionStatus", "") == "ACTIVE",
                method="get",
                timeout=3600,
                interval=45,
                op="deploy",
                url=self.nvcf_fn_deploy_url
            )

            # Clean old versions
            if op == "update" and bool(fn.auto_clean):
                for old_version in fn.old_versions:
                    d_url = f"{self.SCOPE_API_MAP['delete_function']}/functions/{fn.current_id}/versions/{old_version}"
                    self._conf_nvcf(
                        nvcf_type="delete_function",
                        method="DELETE",
                        url=d_url
                    )

    def render_template(self, template_filename, context, template_dir=''):
        template_dir = template_dir or os.getcwd()
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template(template_filename)
        return template.render(context)

    def create(self):
        if len(self.function_creates) >= 1:
            logger.info(f"{self.job_name}: Processing function registrations CREATE")
            self._reconcile(self.function_creates, op="create")
        if len(self.function_updates) >= 1:
            logger.info(f"{self.job_name}: Processing function registrations UPDATE")
            self._reconcile(self.function_updates, op="update")

def get_fn_env_vars():
    env_vars = {}
    for key, value in os.environ.items():
        if key.startswith("FN_") and value.strip():
            env_key = key.lower()
            env_vars[env_key] = value
            logger.info(f"Environment var added: {key} = {value}")
    return env_vars

def main():
    parser = argparse.ArgumentParser(description="Run the NVCF Launcher")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode (skip runner.create())")
    parser.add_argument("--manifest", type=str, help="Path to the YAML manifest file", required=True)
    parser.add_argument("--function-name", type=str, help="Function name(s) to limit the deployment to (comma-separated list or '*')")
    parser.add_argument(
        "--environment", type=str, help='Destination for NVCF deployment matching "type"', required=True
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    runner = NVCFRunner(
        job_name="Launcher",
        env_vars={},
        backend="GitHub",
        function_name=args.function_name,
        environment=args.environment,
        debug_mode=args.debug
    )

    manifest_path = args.manifest
    file_extension = os.path.splitext(manifest_path)[1]

    if file_extension == '.j2':
        with open('launch-list.yml') as file:
            launch_list = yaml.safe_load(file)

        template_dir = os.path.dirname(manifest_path)
        template_filename = os.path.basename(manifest_path)

        # Separate top-level variables and functions
        top_level_vars = {k: v for k, v in launch_list.items() if k != 'functions'}

        # Get environment variables with 'FN_' prefix
        fn_env_vars = get_fn_env_vars()

        if args.function_name:
            function_names = [fn.strip() for fn in args.function_name.split(',')]
            if '*' in function_names:
                launch_list['functions'] = launch_list.get('functions', [])
            else:
                launch_list['functions'] = [
                    fn for fn in launch_list.get('functions', []) 
                    if fn.get('fn_name') in function_names
                ]

        for launch_config in launch_list.get('functions', []):
            # Merge in this order: YAML vars -> function-specific vars -> FN_ env vars
            context = {**top_level_vars, **launch_config, **fn_env_vars}
            
            rendered_manifest = runner.render_template(template_filename, context, template_dir)
            temp_manifest_path = f"manifest-{launch_config.get('fn_name', 'null')}.yml"
            with open(temp_manifest_path, 'w') as temp_manifest:
                temp_manifest.write(rendered_manifest)
            
            if args.debug:
                logger.info(f"Debug mode: Rendered manifest saved to {temp_manifest_path}")
                continue

            process_manifest(runner, temp_manifest_path, args.debug)

    elif file_extension in ['.yml', '.yaml']:
        if not args.debug:
            process_manifest(runner, manifest_path, args.debug)
        else:
            logger.info("Debug mode: Only processing manifest generation.")

    else:
        logger.error("Unsupported manifest file format.")
        sys.exit(1)

def process_manifest(runner, manifest_path, debug_mode):
    try:
        runner._digest_manifest(manifest_path=manifest_path, logger=logger)
        runner._list_nvcf_fn(logger=logger)
        runner.categorize_functions()
        
        if not debug_mode:
            runner.create()
    except FileNotFoundError:
        logger.error(f"Manifest file not found: {manifest_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
