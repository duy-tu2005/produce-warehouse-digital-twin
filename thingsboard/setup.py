#!/usr/bin/env python3
"""Idempotently deploy the Produce Warehouse Digital Twin to ThingsBoard CE.

The script intentionally keeps credentials out of tracked source files.  It
accepts an API key (preferred) or tenant credentials and writes only local,
git-ignored runtime secrets after ThingsBoard has generated the device token.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULE_SCRIPT_DIR = PROJECT_ROOT / "thingsboard" / "rule-scripts"
EXPORT_DIR = PROJECT_ROOT / "thingsboard" / "exports"
ASSET_DIR = PROJECT_ROOT / "thingsboard" / "assets"
FIRMWARE_DIR = PROJECT_ROOT / "firmware"

RULE_CHAIN_NAME = "Produce Warehouse Digital Twin - Processing"
DEVICE_PROFILE_NAME = "ESP32_Environment_Node"
ASSET_PROFILE_NAME = "Produce_Warehouse"
DEVICE_NAME = "ESP32_Env_Node_01"
ASSET_NAME = "Produce_Warehouse_01"
DASHBOARD_TITLE = "Produce Warehouse - Digital Twin"
COMPONENT_VIEWS = {
    "environment": "DHT22_Storage_Racks_View",
    "motion": "PIR_Loading_Door_View",
    "led": "LED_GPIO2_Control_Corner_View",
}

COLORS = {
    "green_dark": "#064e3b",
    "green": "#047857",
    "green_light": "#d1fae5",
    "blue": "#0284c7",
    "cyan": "#0891b2",
    "amber": "#d97706",
    "red": "#dc2626",
    "violet": "#7c3aed",
    "slate": "#475569",
    "card": "#ffffff",
    "background": "#eef7f1",
}


def log(message: str) -> None:
    print(f"[setup] {message}", flush=True)


def read_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


class ThingsBoardClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(normalized)
        if parsed.hostname == "localhost":
            port = f":{parsed.port}" if parsed.port else ""
            normalized = urllib.parse.urlunsplit(
                (parsed.scheme, f"127.0.0.1{port}", parsed.path, parsed.query, parsed.fragment)
            )
        self.base_url = normalized
        # Never send the local ThingsBoard traffic through a Windows/system
        # proxy. urllib's automatic proxy discovery otherwise adds a 20-30 s
        # delay to every localhost request on some machines.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.authorization = f"ApiKey {api_key}" if api_key else None
        if not self.authorization:
            if not username or password is None:
                raise RuntimeError("Provide TB_API_KEY or both TB_USERNAME and TB_PASSWORD.")
            pair = self.request(
                "POST",
                "/api/auth/login",
                {"username": username, "password": password},
                authenticated=False,
            )
            self.authorization = f"Bearer {pair['token']}"

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        query: dict[str, Any] | None = None,
        authenticated: bool = True,
        retries: int = 4,
    ) -> Any:
        url = self.base_url + path
        if query:
            clean_query = {key: value for key, value in query.items() if value is not None}
            url += "?" + urllib.parse.urlencode(clean_query, doseq=True)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if authenticated and self.authorization:
            headers["X-Authorization"] = self.authorization

        for attempt in range(retries):
            request = urllib.request.Request(url, data=payload, headers=headers, method=method)
            try:
                with self.opener.open(request, timeout=90) as response:
                    raw = response.read()
                    if not raw:
                        return None
                    content_type = response.headers.get("Content-Type", "")
                    if "json" in content_type or raw[:1] in (b"{", b"["):
                        return json.loads(raw.decode("utf-8-sig"))
                    return raw.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as error:
                details = error.read().decode("utf-8", errors="replace")
                if error.code >= 500 and attempt + 1 < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"ThingsBoard API {method} {path} failed ({error.code}): {details}"
                ) from error
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt + 1 < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"ThingsBoard API {method} {path} failed: {error}") from error
        raise RuntimeError(f"ThingsBoard API {method} {path} failed after retries")

    def get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, query=query)

    def post(self, path: str, body: Any, query: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, body=body, query=query)


def entity_uuid(entity: dict[str, Any]) -> str:
    value = entity["id"]
    return value if isinstance(value, str) else value["id"]


def entity_id(entity_type: str, value: str) -> dict[str, str]:
    return {"entityType": entity_type, "id": value}


def page_data(client: ThingsBoardClient, path: str, **query: Any) -> list[dict[str, Any]]:
    result = client.get(path, {"pageSize": 1000, "page": 0, **query})
    return result.get("data", [])


def find_by_name(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("name") == name or item.get("title") == name), None)


def read_rule_script(name: str) -> str:
    return (RULE_SCRIPT_DIR / name).read_text(encoding="utf-8")


def ensure_rule_chain(client: ThingsBoardClient) -> dict[str, Any]:
    chains = page_data(client, "/api/ruleChains", type="CORE")
    existing = find_by_name(chains, RULE_CHAIN_NAME)
    if existing:
        log(f"Using existing rule chain: {RULE_CHAIN_NAME}")
        return existing
    chain = client.post(
        "/api/ruleChain",
        {
            "name": RULE_CHAIN_NAME,
            "type": "CORE",
            "root": False,
            "debugMode": False,
            "configuration": None,
            "additionalInfo": {
                "description": "CE-compatible Digital Twin state and anomaly processing for the produce warehouse."
            },
        },
    )
    log(f"Created rule chain: {RULE_CHAIN_NAME}")
    return chain


def node(
    node_type: str,
    name: str,
    version: int,
    configuration: dict[str, Any],
    x: int,
    y: int,
    debug_failures: bool = False,
) -> dict[str, Any]:
    return {
        "type": node_type,
        "name": name,
        "debugSettings": (
            {"failuresEnabled": True, "allEnabled": False, "allEnabledUntil": 0}
            if debug_failures
            else None
        ),
        "singletonMode": False,
        "queueName": None,
        "configurationVersion": version,
        "configuration": configuration,
        "additionalInfo": {"layoutX": x, "layoutY": y},
    }


def transform_config(script: str) -> dict[str, Any]:
    return {
        "scriptLang": "JS",
        "jsScript": script,
        "tbelScript": "return {msg: msg, metadata: metadata, msgType: msgType};",
    }


def filter_config(script: str) -> dict[str, Any]:
    return {"scriptLang": "JS", "jsScript": script, "tbelScript": "return false;"}


def save_ts_config() -> dict[str, Any]:
    return {"defaultTTL": 0, "useServerTs": False, "processingSettings": {"type": "ON_EVERY_MESSAGE"}}


def save_attribute_config(scope: str) -> dict[str, Any]:
    return {
        "processingSettings": {"type": "ON_EVERY_MESSAGE"},
        "scope": scope,
        "notifyDevice": False,
        "sendAttributesUpdatedNotification": False,
        "updateAttributesOnlyOnValueChange": True,
    }


def change_to_parent_asset_config() -> dict[str, Any]:
    return {
        "originatorSource": "RELATED",
        "relationsQuery": {
            "direction": "TO",
            "maxLevel": 1,
            "filters": [
                {"relationType": "Contains", "entityTypes": ["ASSET"], "negate": False}
            ],
            "fetchLastLevelOnly": False,
        },
        "entityType": None,
        "entityNamePattern": None,
    }


def alarm_details_script() -> str:
    return """var details = {
  observed_state: msg.observed_state,
  expected_state: msg.expected_state,
  anomaly_score: msg.anomaly_score,
  health_score: msg.health_score,
  severity: msg.severity,
  last_seen: msg.last_seen
};
try {
  details.detection = JSON.parse(msg.anomaly_details || '{}');
} catch (e) {
  details.detection = {raw: msg.anomaly_details};
}
return details;"""


def create_alarm_config(alarm_type: str, severity: str, dynamic: bool) -> dict[str, Any]:
    return {
        "alarmType": alarm_type,
        "scriptLang": "JS",
        "alarmDetailsBuildJs": alarm_details_script(),
        "alarmDetailsBuildTbel": "return {};",
        "severity": severity,
        "propagate": False,
        "propagateToOwner": False,
        "propagateToTenant": False,
        "useMessageAlarmData": False,
        "overwriteAlarmDetails": True,
        "dynamicSeverity": dynamic,
        "relationTypes": [],
    }


def clear_alarm_config(alarm_type: str) -> dict[str, Any]:
    return {
        "alarmType": alarm_type,
        "scriptLang": "JS",
        "alarmDetailsBuildJs": alarm_details_script(),
        "alarmDetailsBuildTbel": "return {};",
    }


def log_node_config() -> dict[str, Any]:
    script = "return 'Digital Twin message: ' + JSON.stringify(msg);"
    return {"scriptLang": "JS", "jsScript": script, "tbelScript": script}


def deploy_rule_chain_metadata(client: ThingsBoardClient, chain: dict[str, Any]) -> dict[str, Any]:
    classes = {
        "switch": "org.thingsboard.rule.engine.filter.TbMsgTypeSwitchNode",
        "attrs": "org.thingsboard.rule.engine.metadata.TbGetAttributesNode",
        "transform": "org.thingsboard.rule.engine.transform.TbTransformMsgNode",
        "filter": "org.thingsboard.rule.engine.filter.TbJsFilterNode",
        "change": "org.thingsboard.rule.engine.transform.TbChangeOriginatorNode",
        "save_ts": "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode",
        "save_attrs": "org.thingsboard.rule.engine.telemetry.TbMsgAttributesNode",
        "create_alarm": "org.thingsboard.rule.engine.action.TbCreateAlarmNode",
        "clear_alarm": "org.thingsboard.rule.engine.action.TbClearAlarmNode",
        "rpc": "org.thingsboard.rule.engine.rpc.TbSendRPCRequestNode",
        "log": "org.thingsboard.rule.engine.action.TbLogNode",
    }

    enrich_config = {
        "fetchTo": "METADATA",
        "clientAttributeNames": [],
        "sharedAttributeNames": [],
        "serverAttributeNames": [
            "temp_warn_low",
            "temp_warn_high",
            "temp_critical_low",
            "temp_critical_high",
            "humidity_warn_low",
            "humidity_warn_high",
            "humidity_critical_low",
            "humidity_critical_high",
            "temperature_rate_cpm",
            "humidity_rate_ppm",
            "stuck_epsilon",
            "stuck_samples",
            "recovery_clean_windows",
            "actuator_mismatch_samples",
            "expected_led_state",
            "weak_rssi_warning",
            "weak_rssi_critical",
            "expected_state",
            "security_mode",
        ],
        "latestTsKeyNames": [
            "temperature",
            "humidity",
            "sequence",
            "uptime_s",
            "observed_state",
            "anomaly_type",
            "stuck_count",
            "invalid_count",
            "recovery_count",
            "actuator_mismatch_count",
        ],
        "tellFailureIfAbsent": False,
        "getLatestValueWithTs": True,
    }

    attributes_script = "return {msg: msg, metadata: metadata, msgType: 'POST_ATTRIBUTES_REQUEST'};"

    # Node indexes are grouped by flow so the exported chain remains easy to
    # explain in the report and in ThingsBoard's visual editor.
    nodes: list[dict[str, Any]] = [
        # 0: router
        node(classes["switch"], "Message Type Switch", 0, {"version": 0}, 80, 360),

        # 1..12: telemetry -> state -> twin -> alarm
        node(classes["attrs"], "Load thresholds and previous state", 1, enrich_config, 320, 80),
        node(classes["transform"], "Compute Digital Twin state", 0,
             transform_config(read_rule_script("process-telemetry.js")), 570, 80),
        node(classes["save_ts"], "Save enriched device telemetry", 1, save_ts_config(), 830, 20),
        node(classes["change"], "Originator: parent warehouse", 0,
             change_to_parent_asset_config(), 830, 130),
        node(classes["transform"], "Build warehouse twin payload", 0,
             transform_config(read_rule_script("build-twin-payload.js")), 1080, 130),
        node(classes["save_ts"], "Save twin time series", 1, save_ts_config(), 1330, 40),
        node(classes["transform"], "Prepare twin server attributes", 0,
             transform_config(attributes_script), 1330, 130),
        node(classes["save_attrs"], "Save twin server attributes", 3,
             save_attribute_config("SERVER_SCOPE"), 1580, 130),
        node(classes["filter"], "Previous alarm changed?", 0,
             filter_config(read_rule_script("should-clear-previous-alarm.js")), 1330, 240),
        node(classes["clear_alarm"], "Clear previous anomaly alarm", 0,
             clear_alarm_config("${prevAlarmType}"), 1580, 230),
        node(classes["filter"], "Anomaly active?", 0,
             filter_config(read_rule_script("has-anomaly.js")), 1810, 260),
        node(classes["create_alarm"], "Create or update anomaly alarm", 0,
             create_alarm_config("${alarmType}", "${alarmSeverity}", True), 2050, 260,
             debug_failures=True),

        # 13..19: inactivity -> read prior alarm -> OFFLINE twin. After the
        # originator changes, the shared alarm branch clears the prior anomaly
        # and creates/updates CONNECTION_LOST.
        node(classes["transform"], "Build OFFLINE twin state", 0,
             transform_config(read_rule_script("offline-state.js")), 320, 470),
        node(classes["save_ts"], "Save OFFLINE on device", 1, save_ts_config(), 570, 410),
        node(classes["change"], "OFFLINE originator: warehouse", 0,
             change_to_parent_asset_config(), 570, 520),
        node(classes["save_ts"], "Save OFFLINE twin time series", 1, save_ts_config(), 830, 430),
        node(classes["transform"], "Prepare OFFLINE server attributes", 0,
             transform_config(attributes_script), 830, 520),
        node(classes["save_attrs"], "Save OFFLINE twin attributes", 3,
             save_attribute_config("SERVER_SCOPE"), 1080, 520),
        node(classes["attrs"], "Load active anomaly before OFFLINE", 1,
             {
                 "fetchTo": "METADATA",
                 "clientAttributeNames": [],
                 "sharedAttributeNames": [],
                 "serverAttributeNames": [],
                 "latestTsKeyNames": ["anomaly_type"],
                 "tellFailureIfAbsent": False,
                 "getLatestValueWithTs": True,
             }, 320, 470),

        # 20..21: activity only clears the connection alarm. The associated
        # telemetry message is the sole authority for RECOVERY/NORMAL/ANOMALY,
        # preventing a race that could overwrite a real anomaly.
        node(classes["change"], "ACTIVITY originator: warehouse", 0,
             change_to_parent_asset_config(), 320, 730),
        node(classes["clear_alarm"], "Clear CONNECTION_LOST alarm", 0,
             clear_alarm_config("CONNECTION_LOST"), 570, 730),

        # 22..25: standard device traffic
        node(classes["save_attrs"], "Save client attributes", 3,
             save_attribute_config("CLIENT_SCOPE"), 320, 850),
        node(classes["rpc"], "RPC call request", 0, {"timeoutInSeconds": 60}, 320, 950),
        node(classes["log"], "Log RPC response from device", 0, log_node_config(), 570, 950),
        node(classes["log"], "Log other messages", 0, log_node_config(), 320, 1050),

        # 26..28: mirror an outbound setLed RPC into the desired actuator
        # state so telemetry can detect a real command/feedback mismatch.
        node(classes["filter"], "RPC is setLed?", 0,
             filter_config("return msg.method === 'setLed' || msg.method === 'setState';"), 570, 850),
        node(classes["transform"], "Capture expected LED state", 0,
             transform_config("var p=msg.params; var v=false; if(typeof p==='boolean'){v=p;} else if(p && p.state!==undefined){v=p.state===true || p.state==='true';} else if(p && p.value!==undefined){v=p.value===true || p.value==='true';} return {msg:{expected_led_state:v,expected_led_updated_ts:Date.now()},metadata:metadata,msgType:'POST_ATTRIBUTES_REQUEST'};"), 830, 850),
        node(classes["save_attrs"], "Save expected LED state", 3,
             save_attribute_config("SERVER_SCOPE"), 1080, 850),
    ]

    connections: list[dict[str, Any]] = []

    def connect(source: int, target: int, relation: str) -> None:
        connections.append({"fromIndex": source, "toIndex": target, "type": relation})

    connect(0, 1, "Post telemetry")
    connect(1, 2, "Success")
    connect(1, 2, "Failure")
    connect(2, 3, "Success")
    connect(2, 4, "Success")
    connect(4, 5, "Success")
    connect(5, 6, "Success")
    connect(5, 7, "Success")
    connect(7, 8, "Success")
    connect(5, 9, "Success")
    connect(9, 10, "True")
    connect(9, 11, "False")
    connect(9, 11, "Failure")
    connect(10, 11, "Cleared")
    connect(10, 11, "False")
    connect(10, 11, "Failure")
    connect(11, 12, "True")

    connect(0, 19, "Inactivity Event")
    connect(19, 13, "Success")
    connect(19, 13, "Failure")
    connect(13, 14, "Success")
    connect(13, 15, "Success")
    connect(15, 16, "Success")
    connect(15, 17, "Success")
    connect(17, 18, "Success")
    connect(15, 9, "Success")

    connect(0, 20, "Activity Event")
    connect(20, 21, "Success")

    connect(0, 22, "Post attributes")
    connect(0, 23, "RPC Request to Device")
    connect(0, 26, "RPC Request to Device")
    connect(26, 27, "True")
    connect(27, 28, "Success")
    connect(0, 24, "RPC Request from Device")
    connect(0, 25, "Other")

    chain_id = entity_uuid(chain)
    metadata = {
        "ruleChainId": entity_id("RULE_CHAIN", chain_id),
        "firstNodeIndex": 0,
        "nodes": nodes,
        "connections": connections,
        "ruleChainConnections": None,
    }
    saved = client.post("/api/ruleChain/metadata", metadata)
    log(f"Deployed {len(nodes)} rule nodes and {len(connections)} connections")
    return saved


def ensure_device_profile(
    client: ThingsBoardClient, chain: dict[str, Any]
) -> dict[str, Any]:
    profiles = page_data(client, "/api/deviceProfiles")
    existing = find_by_name(profiles, DEVICE_PROFILE_NAME)
    chain_ref = entity_id("RULE_CHAIN", entity_uuid(chain))
    if existing:
        payload = copy.deepcopy(existing)
        payload["description"] = "ESP32 + DHT22 + PIR + GPIO2 LED for the produce warehouse twin"
        payload["defaultRuleChainId"] = chain_ref
    else:
        payload = {
            "name": DEVICE_PROFILE_NAME,
            "description": "ESP32 + DHT22 + PIR + GPIO2 LED for the produce warehouse twin",
            "type": "DEFAULT",
            "transportType": "DEFAULT",
            "provisionType": "DISABLED",
            "defaultRuleChainId": chain_ref,
            "defaultDashboardId": None,
            "defaultQueueName": None,
            "profileData": {
                "configuration": {"type": "DEFAULT"},
                "transportConfiguration": {"type": "DEFAULT"},
                "provisionConfiguration": {"type": "DISABLED", "provisionDeviceSecret": None},
                "alarms": None,
            },
        }
    profile = client.post("/api/deviceProfile", payload)
    log(f"Ready device profile: {DEVICE_PROFILE_NAME}")
    return profile


def ensure_asset_profile(client: ThingsBoardClient) -> dict[str, Any]:
    profiles = page_data(client, "/api/assetProfiles")
    existing = find_by_name(profiles, ASSET_PROFILE_NAME)
    if existing:
        payload = copy.deepcopy(existing)
        payload["description"] = "Digital Twin root asset for a produce cold-storage warehouse"
    else:
        payload = {
            "name": ASSET_PROFILE_NAME,
            "description": "Digital Twin root asset for a produce cold-storage warehouse",
            "defaultRuleChainId": None,
            "defaultDashboardId": None,
            "defaultQueueName": None,
        }
    profile = client.post("/api/assetProfile", payload)
    log(f"Ready asset profile: {ASSET_PROFILE_NAME}")
    return profile


def ensure_asset(client: ThingsBoardClient, profile: dict[str, Any]) -> dict[str, Any]:
    assets = page_data(client, "/api/tenant/assets")
    existing = find_by_name(assets, ASSET_NAME)
    payload: dict[str, Any] = copy.deepcopy(existing) if existing else {}
    payload.update(
        {
            "name": ASSET_NAME,
            "type": ASSET_PROFILE_NAME,
            "label": "Kho bảo quản rau quả số 01",
            "assetProfileId": entity_id("ASSET_PROFILE", entity_uuid(profile)),
            "additionalInfo": {
                "description": "Digital Twin of the produce warehouse defined by the assignment",
                "location": "Laboratory / Wokwi simulation",
                "model": "Asset Contains ESP32 environment node",
            },
        }
    )
    asset = client.post("/api/asset", payload)
    log(f"Ready asset: {ASSET_NAME}")
    return asset


def ensure_device(client: ThingsBoardClient, profile: dict[str, Any]) -> dict[str, Any]:
    devices = page_data(client, "/api/tenant/devices")
    existing = find_by_name(devices, DEVICE_NAME)
    payload: dict[str, Any] = copy.deepcopy(existing) if existing else {}
    payload.update(
        {
            "name": DEVICE_NAME,
            "type": DEVICE_PROFILE_NAME,
            "label": "ESP32 - DHT22, PIR, LED GPIO2",
            "deviceProfileId": entity_id("DEVICE_PROFILE", entity_uuid(profile)),
            "additionalInfo": {
                "description": "Physical layer of the produce warehouse Digital Twin",
                "hardware": "ESP32 DevKit V1 + DHT22 + PIR + LED",
                "firmware": "firmware/sketch.ino",
            },
        }
    )
    device = client.post("/api/device", payload)
    log(f"Ready device: {DEVICE_NAME}")
    return device


def ensure_relation(client: ThingsBoardClient, asset: dict[str, Any], device: dict[str, Any]) -> None:
    relation = {
        "from": entity_id("ASSET", entity_uuid(asset)),
        "to": entity_id("DEVICE", entity_uuid(device)),
        "type": "Contains",
        "typeGroup": "COMMON",
        "additionalInfo": {
            "description": "The warehouse contains the ESP32 environment sensing and LED actuator node"
        },
    }
    client.post("/api/v2/relation", relation)
    log("Ready relation: Produce_Warehouse_01 --Contains--> ESP32_Env_Node_01")


def set_server_attributes(
    client: ThingsBoardClient, entity_type: str, entity_uuid_value: str, values: dict[str, Any]
) -> None:
    client.post(
        f"/api/plugins/telemetry/{entity_type}/{entity_uuid_value}/attributes/SERVER_SCOPE",
        values,
    )


def set_timeseries(
    client: ThingsBoardClient, entity_type: str, entity_uuid_value: str, values: dict[str, Any]
) -> None:
    client.post(
        f"/api/plugins/telemetry/{entity_type}/{entity_uuid_value}/timeseries/ANY",
        values,
    )


def configure_entities(
    client: ThingsBoardClient, asset: dict[str, Any], device: dict[str, Any]
) -> None:
    device_attrs = {
        "board": "ESP32 DevKit V1",
        "sensors": "DHT22, PIR",
        "actuator": "LED GPIO2",
        "dht_gpio": 15,
        "pir_gpio": 13,
        "led_gpio": 2,
        "sample_period_s": 5,
        "map_env_x": 0.30,
        "map_env_y": 0.31,
        "map_env_type": "environment",
        "map_motion_x": 0.19,
        "map_motion_y": 0.58,
        "map_motion_type": "motion",
        "map_led_x": 0.87,
        "map_led_y": 0.71,
        "map_led_type": "led",
        # 5 s timeout + 5 s state-check cadence leaves processing headroom
        # while keeping connection-loss detection below the required 15 s.
        "inactivityTimeout": 5000,
        "expected_state": "NORMAL",
        "security_mode": "DISARMED",
        "temp_warn_low": 18,
        "temp_warn_high": 26,
        "temp_critical_low": 15,
        "temp_critical_high": 30,
        "humidity_warn_low": 55,
        "humidity_warn_high": 75,
        "humidity_critical_low": 45,
        "humidity_critical_high": 85,
        "temperature_rate_cpm": 2,
        "humidity_rate_ppm": 10,
        "stuck_epsilon": 0.01,
        "stuck_samples": 12,
        "recovery_clean_windows": 3,
        "actuator_mismatch_samples": 3,
        "expected_led_state": False,
        "weak_rssi_warning": -80,
        "weak_rssi_critical": -90,
    }
    asset_attrs = {
        "twin_role": "produce-warehouse",
        "model_version": "2.0.0",
        "description": "Digital Twin kho bảo quản rau quả",
        "expected_state": "NORMAL",
        "observed_state": "INIT",
        "health_score": 100,
        "anomaly_score": 0,
        "anomaly_type": "NONE",
        "anomaly": False,
        "severity": "NONE",
        "online": False,
        "state_match": False,
    }
    set_server_attributes(client, "DEVICE", entity_uuid(device), device_attrs)
    set_server_attributes(client, "ASSET", entity_uuid(asset), asset_attrs)

    now = int(time.time() * 1000)
    baseline_device = {
        "temperature": 22.0,
        "humidity": 65.0,
        "motion": False,
        "rssi": -52,
        "sequence": 0,
        "uptime_s": 0,
        "led_state": False,
        "sensor_valid": True,
        "observed_state": "INIT",
        "expected_state": "NORMAL",
        "health_score": 100,
        "anomaly_score": 0,
        "anomaly_type": "NONE",
        "anomaly": False,
        "severity": "NONE",
        "online": False,
        "last_seen": now,
    }
    baseline_asset = {
        "last_seen": now,
        "observed_state": "INIT",
        "expected_state": "NORMAL",
        "health_score": 100,
        "anomaly_score": 0,
        "anomaly_type": "NONE",
        "anomaly": False,
        "severity": "NONE",
        "online": False,
        "state_match": False,
    }
    set_timeseries(client, "DEVICE", entity_uuid(device), baseline_device)
    set_timeseries(client, "ASSET", entity_uuid(asset), baseline_asset)
    log("Configured thresholds, inactivity timeout, and baseline twin state")


def ensure_component_views(
    client: ThingsBoardClient, device: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Expose three logical twin components without duplicating device telemetry."""
    existing_views = page_data(client, "/api/tenant/entityViews")
    definitions = {
        "environment": {
            "type": "DHT22 sensor",
            "timeseries": ["temperature", "humidity", "rssi", "sensor_valid"],
            "server_attributes": ["map_env_x", "map_env_y", "map_env_type"],
            "attribute_values": {
                "map_env_x": 0.30,
                "map_env_y": 0.31,
                "map_env_type": "environment",
            },
            "description": "DHT22 environment sensor mounted beside the storage racks",
        },
        "motion": {
            "type": "PIR sensor",
            "timeseries": ["motion"],
            "server_attributes": ["map_motion_x", "map_motion_y", "map_motion_type"],
            "attribute_values": {
                "map_motion_x": 0.19,
                "map_motion_y": 0.58,
                "map_motion_type": "motion",
            },
            "description": "PIR motion sensor mounted beside the warehouse loading door",
        },
        "led": {
            "type": "LED actuator",
            "timeseries": ["led_state"],
            "server_attributes": ["map_led_x", "map_led_y", "map_led_type"],
            "attribute_values": {
                "map_led_x": 0.87,
                "map_led_y": 0.71,
                "map_led_type": "led",
            },
            "description": "GPIO2 LED actuator shown at the warehouse control corner",
        },
    }
    views: dict[str, dict[str, Any]] = {}
    for kind, definition in definitions.items():
        name = COMPONENT_VIEWS[kind]
        existing = find_by_name(existing_views, name)
        payload: dict[str, Any] = copy.deepcopy(existing) if existing else {}
        payload.update(
            {
                "name": name,
                "type": definition["type"],
                "entityId": entity_id("DEVICE", entity_uuid(device)),
                "startTimeMs": 0,
                "endTimeMs": 0,
                "keys": {
                    "timeseries": definition["timeseries"],
                    "attributes": {
                        "cs": [],
                        "ss": definition["server_attributes"],
                        "sh": [],
                    },
                },
                "additionalInfo": {"description": definition["description"]},
            }
        )
        views[kind] = client.post("/api/entityView", payload)
        # Entity View attribute propagation can be eventually consistent when
        # several views of one device are updated in quick succession.  Map
        # coordinates are view metadata, so persist them on each view too.
        set_server_attributes(
            client,
            "ENTITY_VIEW",
            entity_uuid(views[kind]),
            definition["attribute_values"],
        )
        log(f"Ready entity view: {name}")
    return views


def ensure_component_relations(
    client: ThingsBoardClient,
    asset: dict[str, Any],
    component_views: dict[str, dict[str, Any]],
) -> None:
    for kind, view in component_views.items():
        client.post(
            "/api/v2/relation",
            {
                "from": entity_id("ASSET", entity_uuid(asset)),
                "to": entity_id("ENTITY_VIEW", entity_uuid(view)),
                "type": "Contains",
                "typeGroup": "COMMON",
                "additionalInfo": {
                    "description": f"Warehouse contains the logical {kind} twin component"
                },
            },
        )
    log("Ready component relations: warehouse --Contains--> DHT22, PIR, LED views")

def deterministic_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"thingsboard://produce-warehouse/{label}"))


def image_data_uri(path: Path) -> str:
    """Embed a project image so the dashboard remains portable after export."""
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix)
    if not mime:
        raise RuntimeError(f"Unsupported dashboard image format: {path}")
    if not path.exists():
        raise RuntimeError(f"Dashboard image is missing: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def widget_default(client: ThingsBoardClient, fqn: str) -> tuple[str, str, dict[str, Any]]:
    widget_type = client.get("/api/widgetType", {"fqn": f"system.{fqn}"})
    descriptor = widget_type["descriptor"]
    default_config = descriptor.get("defaultConfig", "{}")
    config = json.loads(default_config) if isinstance(default_config, str) else copy.deepcopy(default_config)
    return widget_type["fqn"], descriptor["type"], config


def data_key(
    name: str,
    label: str,
    color: str,
    key_type: str = "timeseries",
    units: str | None = None,
    decimals: int | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": key_type,
        "label": label,
        "color": color,
        "settings": settings or {},
        "aggregationType": None,
        "units": units,
        "decimals": decimals,
        "usePostProcessing": None,
        "postFuncBody": None,
    }


def set_common_widget_style(config: dict[str, Any], title: str, show_title: bool = True) -> None:
    config["title"] = title
    config["showTitle"] = show_title
    config["backgroundColor"] = COLORS["card"]
    config["color"] = "#1f2937"
    config["dropShadow"] = True
    config["enableFullscreen"] = True
    config["borderRadius"] = "12px"
    config["margin"] = "0px"
    config["padding"] = config.get("padding", "8px")
    config["titleColor"] = COLORS["green_dark"]
    config["titleFont"] = {
        "size": 16,
        "sizeUnit": "px",
        "family": "Roboto",
        "weight": "600",
        "style": "normal",
        "lineHeight": "24px",
    }
    settings = config.setdefault("settings", {})
    settings["background"] = {
        "type": "color",
        "color": COLORS["card"],
        "overlay": {"enabled": False, "color": "rgba(255,255,255,0.72)", "blur": 3},
    }


def make_widget(
    widget_id: str,
    fqn: str,
    widget_type: str,
    config: dict[str, Any],
    size_x: int,
    size_y: int,
) -> dict[str, Any]:
    return {
        "type": widget_type,
        "sizeX": size_x,
        "sizeY": size_y,
        "config": config,
        "id": widget_id,
        "typeFullFqn": f"system.{fqn}",
    }


def build_dashboard_configuration(
    client: ThingsBoardClient,
    asset: dict[str, Any],
    device: dict[str, Any],
    component_views: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    asset_alias = deterministic_uuid("alias-warehouse")
    device_alias = deterministic_uuid("alias-device")
    environment_alias = deterministic_uuid("alias-device-environment")
    motion_alias = deterministic_uuid("alias-device-motion")
    led_alias = deterministic_uuid("alias-device-led")
    def single_entity_filter(entity_type: str, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "singleEntity",
            "resolveMultiple": False,
            "singleEntity": entity_id(entity_type, entity_uuid(item)),
        }

    device_filter = single_entity_filter("DEVICE", device)
    aliases = {
        asset_alias: {
            "id": asset_alias,
            "alias": ASSET_NAME,
            "filter": {
                "type": "singleEntity",
                "resolveMultiple": False,
                "singleEntity": entity_id("ASSET", entity_uuid(asset)),
            },
        },
        device_alias: {
            "id": device_alias,
            "alias": DEVICE_NAME,
            "filter": device_filter,
        },
        environment_alias: {
            "id": environment_alias,
            "alias": "DHT22 · Khu kệ hàng",
            "filter": single_entity_filter("ENTITY_VIEW", component_views["environment"]),
        },
        motion_alias: {
            "id": motion_alias,
            "alias": "PIR · Cửa nhập kho",
            "filter": single_entity_filter("ENTITY_VIEW", component_views["motion"]),
        },
        led_alias: {
            "id": led_alias,
            "alias": "LED GPIO2 · Góc điều khiển",
            "filter": single_entity_filter("ENTITY_VIEW", component_views["led"]),
        },
    }

    widgets: dict[str, Any] = {}
    layout: dict[str, Any] = {}

    def add(label: str, widget: dict[str, Any], row: int, col: int, sx: int, sy: int) -> None:
        widget_id = deterministic_uuid("widget-" + label)
        widget["id"] = widget_id
        widget["sizeX"] = sx
        widget["sizeY"] = sy
        widgets[widget_id] = widget
        layout[widget_id] = {"sizeX": sx, "sizeY": sy, "row": row, "col": col}

    image_map_fqn, image_map_type, image_map_cfg = widget_default(client, "maps_v2.image_map")
    set_common_widget_style(
        image_map_cfg,
        "Sơ đồ kho tương tác — nhấn vào cảm biến để xem thông số",
        show_title=True,
    )
    image_map_cfg["padding"] = "0px"
    image_map_cfg["datasources"] = [
        {
            "type": "entity",
            "name": "DHT22 · Khu kệ hàng",
            "entityAliasId": environment_alias,
            "dataKeys": [
                data_key("map_env_x", "xPos", COLORS["blue"], key_type="attribute", decimals=2),
                data_key("map_env_y", "yPos", COLORS["green"], key_type="attribute", decimals=2),
                data_key("map_env_type", "markerType", COLORS["slate"], key_type="attribute"),
                data_key("temperature", "temperature", COLORS["red"], units="°C", decimals=1),
                data_key("humidity", "humidity", COLORS["blue"], units="%", decimals=1),
                data_key("rssi", "rssi", COLORS["violet"], units="dBm", decimals=0),
                data_key("sensor_valid", "sensor_valid", COLORS["green"]),
            ],
        },
        {
            "type": "entity",
            "name": "PIR · Cửa nhập kho",
            "entityAliasId": motion_alias,
            "dataKeys": [
                data_key("map_motion_x", "xPos", COLORS["blue"], key_type="attribute", decimals=2),
                data_key("map_motion_y", "yPos", COLORS["green"], key_type="attribute", decimals=2),
                data_key("map_motion_type", "markerType", COLORS["slate"], key_type="attribute"),
                data_key("motion", "motion", COLORS["amber"]),
            ],
        },
        {
            "type": "entity",
            "name": "LED GPIO2 · Góc điều khiển",
            "entityAliasId": led_alias,
            "dataKeys": [
                data_key("map_led_x", "xPos", COLORS["blue"], key_type="attribute", decimals=2),
                data_key("map_led_y", "yPos", COLORS["green"], key_type="attribute", decimals=2),
                data_key("map_led_type", "markerType", COLORS["slate"], key_type="attribute"),
                data_key("led_state", "led_state", COLORS["amber"]),
            ],
        },
    ]
    image_map_cfg["settings"].update(
        {
            "provider": "image-map",
            "mapImageUrl": image_data_uri(ASSET_DIR / "warehouse-floorplan.png"),
            "xPosKeyName": "xPos",
            "yPosKeyName": "yPos",
            "fitMapBounds": True,
            "useDefaultCenterPosition": False,
            "disableScrollZooming": False,
            "disableDoubleClickZooming": False,
            "disableZoomControl": False,
            "markerOffsetX": 0.5,
            "markerOffsetY": 1,
            "draggableMarker": False,
            "showLabel": True,
            "useLabelFunction": True,
            "label": "${entityName}",
            "labelFunction": (
                "var kind=dsData[dsIndex]['markerType'];"
                "if(kind==='motion'){return 'PIR · Cửa nhập kho';}"
                "if(kind==='led'){return 'LED GPIO2 · Góc điều khiển';}"
                "return 'DHT22 · Khu kệ hàng';"
            ),
            "showTooltip": True,
            "showTooltipAction": "click",
            "autocloseTooltip": True,
            "useTooltipFunction": True,
            "tooltipPattern": (
                "<b>${entityName}</b><br/>"
                "Nhiệt độ: ${temperature:1} °C<br/>Độ ẩm: ${humidity:1} %"
            ),
            "tooltipFunction": (
                "var d=dsData[dsIndex];var kind=d['markerType'];"
                "var head=\"<div style='min-width:235px;font-family:Roboto,sans-serif'>\";"
                "var title=\"<div style='font-size:17px;font-weight:700;color:#064e3b;margin-bottom:10px'>\";"
                "if(kind==='motion'){return head+title+'PIR · Cửa nhập kho</div>'"
                "+\"<div style='display:flex;justify-content:space-between;gap:18px'><span>🚶 Chuyển động</span><b>\""
                "+d['motion']+'</b></div></div>'; }"
                "if(kind==='led'){return head+title+'LED GPIO2 · Góc điều khiển</div>'"
                "+\"<div style='display:flex;justify-content:space-between;gap:18px'><span>💡 Trạng thái đèn</span><b>\""
                "+d['led_state']+\"</b></div><div style='margin-top:10px;color:#475569'>Dùng công tắc Điều khiển đèn GPIO2 bên dưới để bật/tắt.</div></div>\"; }"
                "return head+title+'DHT22 · Khu kệ hàng</div>'"
                "+\"<div style='display:grid;grid-template-columns:1fr auto;gap:7px 18px'>\""
                "+\"<span>🌡️ Nhiệt độ</span><b>\"+d['temperature']+\" °C</b>\""
                "+\"<span>💧 Độ ẩm</span><b>\"+d['humidity']+\" %</b>\""
                "+\"<span>📶 Wi-Fi</span><b>\"+d['rssi']+\" dBm</b>\""
                "+\"<span>✅ DHT22 hợp lệ</span><b>\"+d['sensor_valid']+\"</b></div></div>\";"
            ),
            "tooltipOffsetX": 0,
            "tooltipOffsetY": -1,
            "color": COLORS["blue"],
            "useColorFunction": True,
            "colorFunction": (
                "var d=dsData[dsIndex];var kind=d['markerType'];"
                "if(kind==='motion'){return d['motion'] ? '#dc2626' : '#d97706';}"
                "if(kind==='led'){"
                "var raw=d['led_state'];var on=(raw===true||raw===1||raw==='true'||raw==='1');"
                "window.__warehouseLedOn=on;"
                "var applyLight=function(){document.querySelectorAll('.leaflet-image-layer').forEach(function(img){"
                "if((img.getAttribute('src')||'').indexOf('data:image/')===0){"
                "img.style.transition='filter 450ms ease,opacity 450ms ease';"
                "img.style.filter=on?'brightness(1.08) saturate(1.05)':'brightness(0.38) saturate(0.62)';"
                "img.style.opacity=on?'1':'0.88';}});};"
                "setTimeout(applyLight,0);setTimeout(applyLight,300);"
                "return on ? '#16a34a' : '#7c3aed';}"
                "return '#0284c7';"
            ),
            "useMarkerImageFunction": False,
            "markerImageSize": 46,
            "showPolygon": False,
            "showCircle": False,
        }
    )
    image_map_cfg["titleIcon"] = "warehouse"
    image_map_cfg["iconColor"] = COLORS["green"]
    image_map_cfg["borderRadius"] = "12px"
    add(
        "warehouse-interactive-map",
        make_widget("", image_map_fqn, image_map_type, image_map_cfg, 18, 9),
        0,
        0,
        18,
        9,
    )

    card_fqn, card_type, card_base = widget_default(client, "cards.value_card")

    def value_card(
        title: str,
        alias_id: str,
        entity_name: str,
        key_name: str,
        icon: str,
        color: str,
        units: str | None = None,
        decimals: int | None = None,
        key_type: str = "timeseries",
    ) -> dict[str, Any]:
        cfg = copy.deepcopy(card_base)
        cfg["datasources"] = [
            {
                "type": "entity",
                "name": entity_name,
                "entityAliasId": alias_id,
                "dataKeys": [
                    data_key(key_name, title, color, key_type=key_type, units=units, decimals=decimals)
                ],
                "alarmFilterConfig": {"statusList": ["ACTIVE"]},
            }
        ]
        set_common_widget_style(cfg, title, show_title=False)
        cfg["units"] = units or ""
        cfg["decimals"] = decimals
        cfg["settings"].update(
            {
                "labelPosition": "top",
                "layout": "horizontal",
                "showLabel": True,
                "showIcon": True,
                "icon": icon,
                "iconSize": 38,
                "iconSizeUnit": "px",
                "iconColor": {"type": "constant", "color": color},
                "valueColor": {"type": "constant", "color": COLORS["green_dark"]},
                "labelColor": {"type": "constant", "color": COLORS["slate"]},
                "valueFont": {
                    "family": "Roboto",
                    "size": 28,
                    "sizeUnit": "px",
                    "style": "normal",
                    "weight": "600",
                },
                "showDate": False,
            }
        )
        return make_widget("", card_fqn, card_type, cfg, 6, 4)

    # Compact operational summary in the top-right corner.  Detailed sensor
    # readings remain available from the three interactive map markers.
    add("online", value_card("Kết nối", asset_alias, ASSET_NAME, "online", "wifi", COLORS["green"]), 0, 18, 6, 3)
    add("health", value_card("Điểm sức khỏe", asset_alias, ASSET_NAME, "health_score", "health_and_safety", COLORS["green"], "%", 0), 3, 18, 6, 3)
    add("observed", value_card("Trạng thái Digital Twin", asset_alias, ASSET_NAME, "observed_state", "visibility", COLORS["blue"]), 6, 18, 6, 3)

    switch_fqn, switch_type, switch_cfg = widget_default(client, "control_widgets.switch_control")
    set_common_widget_style(switch_cfg, "Điều khiển đèn GPIO2", show_title=True)
    # RPC widgets resolve their target through the alias-id list.  The
    # `targetDeviceAliases` field in the system default is only a legacy UI
    # placeholder and does not enable the widget subscription by itself.
    switch_cfg["targetDeviceAliasIds"] = [device_alias]
    switch_cfg["backgroundColor"] = COLORS["card"]
    switch_cfg["settings"].update(
        {
            "requestTimeout": 5000,
            "initialValue": False,
            "retrieveValueMethod": "timeseries",
            "valueKey": "led_state",
            "getValueMethod": "getLed",
            "setValueMethod": "setLed",
            "showOnOffLabels": True,
            "title": "LED GPIO2",
        }
    )
    add("led-switch", make_widget("", switch_fqn, switch_type, switch_cfg, 6, 7), 9, 18, 6, 7)

    chart_fqn, chart_type, chart_base = widget_default(client, "time_series_chart")

    def chart(title: str, alias_id: str, entity_name: str, keys: list[dict[str, Any]]) -> dict[str, Any]:
        cfg = copy.deepcopy(chart_base)
        cfg["datasources"] = [
            {
                "type": "entity",
                "name": entity_name,
                "entityAliasId": alias_id,
                "dataKeys": keys,
                "alarmFilterConfig": {"statusList": ["ACTIVE"]},
                "latestDataKeys": [],
            }
        ]
        set_common_widget_style(cfg, title, show_title=True)
        # TB 4.3.1 reliably initializes entity time-series subscriptions when
        # the chart owns a complete time window. Reusing the abbreviated
        # dashboard-level window left the axes visible but the series empty.
        cfg["useDashboardTimewindow"] = False
        cfg["timewindow"] = {
            "realtime": {
                "realtimeType": 0,
                "timewindowMs": 3_600_000,
                "interval": 30_000,
                "quickInterval": "CURRENT_DAY",
            },
            "aggregation": {"type": "AVG", "limit": 25_000},
            "selectedTab": 0,
            "timezone": None,
            "hideTimezone": False,
            "hideAggInterval": False,
            "hideAggregation": False,
        }
        cfg["displayTimewindow"] = True
        cfg["settings"]["showLegend"] = True
        cfg["settings"]["dataZoom"] = True
        return make_widget("", chart_fqn, chart_type, cfg, 12, 7)

    add(
        "environment-history",
        chart(
            "Lịch sử môi trường",
            device_alias,
            DEVICE_NAME,
            [
                data_key("temperature", "Nhiệt độ", COLORS["red"], units="°C", decimals=1, settings={"type": "line", "yAxisId": "default"}),
                data_key("humidity", "Độ ẩm", COLORS["blue"], units="%", decimals=1, settings={"type": "line", "yAxisId": "default"}),
            ],
        ),
        9,
        0,
        6,
        7,
    )
    add(
        "connectivity-history",
        chart(
            "Lịch sử cường độ Wi-Fi",
            device_alias,
            DEVICE_NAME,
            [
                data_key("rssi", "RSSI", COLORS["violet"], units="dBm", decimals=0, settings={"type": "line", "yAxisId": "default"}),
            ],
        ),
        9,
        6,
        6,
        7,
    )
    add(
        "twin-history",
        chart(
            "Lịch sử sức khỏe Digital Twin",
            asset_alias,
            ASSET_NAME,
            [
                data_key("health_score", "Health score", COLORS["green"], units="%", decimals=0, settings={"type": "line", "yAxisId": "default"}),
                data_key("anomaly_score", "Anomaly score", COLORS["red"], decimals=0, settings={"type": "line", "yAxisId": "default"}),
            ],
        ),
        9,
        12,
        6,
        7,
    )

    # Keep the alarm/event history below the three charts so the operational
    # overview remains compact while the Digital Twin evidence is still
    # visible in the same dashboard. The rule chain changes the originator
    # to the warehouse Asset before creating alarms, so filtering by asset
    # shows both active and cleared alarms for this twin.
    alarm_fqn, alarm_type, alarm_cfg = widget_default(client, "alarm_widgets.alarms_table")
    set_common_widget_style(alarm_cfg, "Cảnh báo Digital Twin", show_title=True)
    alarm_cfg["alarmSource"]["entityAliasId"] = asset_alias
    alarm_cfg["alarmSource"]["name"] = "warehouse-alarms"
    alarm_cfg["alarmSearchStatus"] = "ANY"
    alarm_cfg["settings"].update(
        {
            "alarmsTitle": "Cảnh báo Digital Twin",
            "displayDetails": True,
            "displayActivity": True,
            "displayPagination": True,
            "defaultPageSize": 10,
            "defaultSortOrder": "-createdTime",
            "enableSearch": True,
            "enableFilter": True,
            "allowAcknowledgment": True,
            "allowClear": True,
            "allowAssign": False,
        }
    )
    add(
        "digital-twin-alarms",
        make_widget("", alarm_fqn, alarm_type, alarm_cfg, 24, 8),
        16,
        0,
        24,
        8,
    )

    return {
        "widgets": widgets,
        "states": {
            "default": {
                "name": "Tổng quan kho bảo quản",
                "root": True,
                "layouts": {
                    "main": {
                        "widgets": layout,
                        "gridSettings": {
                            "backgroundColor": COLORS["background"],
                            "color": "rgba(0,0,0,0.87)",
                            "columns": 24,
                            "backgroundSizeMode": "100%",
                            "autoFillHeight": False,
                            "mobileAutoFillHeight": False,
                            "mobileRowHeight": 70,
                            "margin": 10,
                            "outerMargin": True,
                            "layoutType": "default",
                        },
                    }
                },
            }
        },
        "entityAliases": aliases,
        "timewindow": {
            "selectedTab": 0,
            "realtime": {"realtimeType": 0, "interval": 5000, "timewindowMs": 3600000},
            "aggregation": {"type": "AVG"},
        },
        "settings": {
            "stateControllerId": "entity",
            "showTitle": True,
            "showDashboardsSelect": True,
            "showEntitiesSelect": False,
            "showDashboardTimewindow": True,
            "showDashboardExport": True,
            "toolbarAlwaysOpen": True,
            "titleColor": COLORS["green_dark"],
            "showDashboardLogo": False,
            "hideToolbar": False,
            "showFilters": True,
            "dashboardCss": ".tb-dashboard { background: #eef7f1; }",
        },
        "filters": {},
    }


def ensure_dashboard(
    client: ThingsBoardClient,
    asset: dict[str, Any],
    device: dict[str, Any],
    component_views: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    dashboards = page_data(client, "/api/tenant/dashboards")
    existing = find_by_name(dashboards, DASHBOARD_TITLE)
    configuration = build_dashboard_configuration(client, asset, device, component_views)
    payload: dict[str, Any] = copy.deepcopy(existing) if existing else {}
    payload.update(
        {
            "title": DASHBOARD_TITLE,
            "configuration": configuration,
            "mobileHide": False,
            "mobileOrder": None,
        }
    )
    dashboard = client.post("/api/dashboard", payload)
    log(f"Ready dashboard: {DASHBOARD_TITLE} ({len(configuration['widgets'])} widgets)")
    return dashboard


def get_device_token(client: ThingsBoardClient, device: dict[str, Any]) -> str:
    credentials = client.get(f"/api/device/{entity_uuid(device)}/credentials")
    token = credentials.get("credentialsId")
    if not token:
        raise RuntimeError("ThingsBoard did not return an access-token credential for the device.")
    return token


def write_local_runtime_files(
    base_url: str,
    mqtt_host: str,
    token: str,
    api_key: str | None,
    chain: dict[str, Any],
    asset: dict[str, Any],
    device: dict[str, Any],
    dashboard: dict[str, Any],
) -> None:
    secrets = f'''#pragma once

// Generated by thingsboard/setup.py. This file is intentionally ignored by Git.
constexpr char WIFI_SSID[] = "Wokwi-GUEST";
constexpr char WIFI_PASSWORD[] = "";
constexpr char TB_MQTT_HOST[] = "{mqtt_host}";
constexpr uint16_t TB_MQTT_PORT = 1883;
constexpr char TB_DEVICE_TOKEN[] = "{token}";
'''
    (FIRMWARE_DIR / "secrets.h").write_text(secrets, encoding="utf-8", newline="\n")

    env_lines = [
        f"TB_BASE_URL={base_url}",
        f"TB_MQTT_HOST={mqtt_host}",
        f"TB_DEVICE_TOKEN={token}",
        f"TB_RULE_CHAIN_ID={entity_uuid(chain)}",
        f"TB_ASSET_ID={entity_uuid(asset)}",
        f"TB_DEVICE_ID={entity_uuid(device)}",
        f"TB_DASHBOARD_ID={entity_uuid(dashboard)}",
    ]
    if api_key:
        env_lines.insert(1, f"TB_API_KEY={api_key}")
    (PROJECT_ROOT / ".env.local").write_text("\n".join(env_lines) + "\n", encoding="utf-8", newline="\n")
    log("Generated local firmware/secrets.h and .env.local (both git-ignored)")


def export_artifacts(
    client: ThingsBoardClient,
    chain: dict[str, Any],
    rule_metadata: dict[str, Any],
    device_profile: dict[str, Any],
    asset_profile: dict[str, Any],
    asset: dict[str, Any],
    device: dict[str, Any],
    component_views: dict[str, dict[str, Any]],
    dashboard: dict[str, Any],
) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "rule-chain.json": chain,
        "rule-chain-metadata.json": rule_metadata,
        "device-profile.json": device_profile,
        "asset-profile.json": asset_profile,
        "asset.json": asset,
        "device.json": device,
        "entity-view-environment.json": component_views["environment"],
        "entity-view-motion.json": component_views["motion"],
        "entity-view-led.json": component_views["led"],
        "dashboard.json": dashboard,
    }
    for filename, data in artifacts.items():
        (EXPORT_DIR / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
    manifest = {
        "project": "Produce Warehouse Digital Twin",
        "thingsboardEdition": "Community Edition compatible",
        "generatedAt": int(time.time() * 1000),
        "entities": {
            "ruleChain": {"name": RULE_CHAIN_NAME, "id": entity_uuid(chain)},
            "asset": {"name": ASSET_NAME, "id": entity_uuid(asset)},
            "device": {"name": DEVICE_NAME, "id": entity_uuid(device)},
            "entityViews": {
                kind: {"name": COMPONENT_VIEWS[kind], "id": entity_uuid(view)}
                for kind, view in component_views.items()
            },
            "dashboard": {"name": DASHBOARD_TITLE, "id": entity_uuid(dashboard)},
        },
        "relations": [
            f"{ASSET_NAME} --Contains--> {DEVICE_NAME}",
            *[
                f"{ASSET_NAME} --Contains--> {COMPONENT_VIEWS[kind]}"
                for kind in component_views
            ],
        ],
        "containsSecrets": False,
    }
    (EXPORT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    log("Exported sanitized ThingsBoard artifacts to thingsboard/exports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None, help="ThingsBoard URL, default http://localhost:8080")
    parser.add_argument("--api-key", default=None, help="Tenant API key; prefer TB_API_KEY in .env.local")
    parser.add_argument("--username", default=None, help="Tenant administrator email")
    parser.add_argument("--password", default=None, help="Tenant administrator password")
    parser.add_argument(
        "--mqtt-host",
        default=None,
        help="MQTT hostname written to firmware; Wokwi VS Code default is host.wokwi.internal",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local_env = read_env_file(PROJECT_ROOT / ".env.local")
    base_url = args.base_url or os.getenv("TB_BASE_URL") or local_env.get("TB_BASE_URL") or "http://localhost:8080"
    api_key = args.api_key or os.getenv("TB_API_KEY") or local_env.get("TB_API_KEY")
    username = args.username or os.getenv("TB_USERNAME") or local_env.get("TB_USERNAME")
    password = args.password or os.getenv("TB_PASSWORD") or local_env.get("TB_PASSWORD")
    mqtt_host = args.mqtt_host or os.getenv("TB_MQTT_HOST") or local_env.get("TB_MQTT_HOST") or "host.wokwi.internal"

    log(f"Connecting to {base_url}")
    client = ThingsBoardClient(base_url, api_key=api_key, username=username, password=password)
    current_user = client.get("/api/auth/user")
    if current_user.get("authority") != "TENANT_ADMIN":
        raise RuntimeError("The setup requires a TENANT_ADMIN account or API key.")

    chain = ensure_rule_chain(client)
    rule_metadata = deploy_rule_chain_metadata(client, chain)
    device_profile = ensure_device_profile(client, chain)
    asset_profile = ensure_asset_profile(client)
    asset = ensure_asset(client, asset_profile)
    device = ensure_device(client, device_profile)
    ensure_relation(client, asset, device)
    configure_entities(client, asset, device)
    component_views = ensure_component_views(client, device)
    ensure_component_relations(client, asset, component_views)
    dashboard = ensure_dashboard(client, asset, device, component_views)
    token = get_device_token(client, device)
    write_local_runtime_files(base_url, mqtt_host, token, api_key, chain, asset, device, dashboard)
    export_artifacts(
        client,
        chain,
        rule_metadata,
        device_profile,
        asset_profile,
        asset,
        device,
        component_views,
        dashboard,
    )

    log("Deployment completed successfully")
    log(f"Dashboard navigation: Dashboards -> {DASHBOARD_TITLE}")
    log("Device access token was generated locally and was not printed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise
    except Exception as error:  # concise CLI failure with a non-zero exit code
        print(f"[setup] ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
