function asNumber(value, fallback) {
    var parsed = parseFloat(value);
    return isFinite(parsed) ? parsed : fallback;
}

function asInteger(value, fallback) {
    var parsed = parseInt(value, 10);
    return isFinite(parsed) ? parsed : fallback;
}

function asBoolean(value, fallback) {
    if (value === true || value === "true") {
        return true;
    }
    if (value === false || value === "false") {
        return false;
    }
    return fallback;
}

function latestValue(key, fallback) {
    var raw = metadata[key];
    if (raw === null || raw === undefined || raw === "") {
        return { present: false, value: fallback, ts: 0 };
    }
    try {
        var object = typeof raw === "string" ? JSON.parse(raw) : raw;
        if (object !== null && typeof object === "object" && object.value !== undefined) {
            return {
                present: true,
                value: object.value,
                ts: asInteger(object.ts, 0)
            };
        }
    } catch (ignore) {
        // Older server versions may return only the raw value.
    }
    return { present: true, value: raw, ts: 0 };
}

function configNumber(key, fallback) {
    return asNumber(metadata["ss_" + key], fallback);
}

function addCandidate(candidates, type, score, details) {
    candidates.push({ type: type, score: score, details: details || {} });
}

function severityForScore(score) {
    if (score >= 80) {
        return "CRITICAL";
    }
    if (score >= 50) {
        return "HIGH";
    }
    if (score >= 20) {
        return "WARNING";
    }
    return "NONE";
}

function alarmSeverity(severity) {
    if (severity === "CRITICAL") {
        return "CRITICAL";
    }
    if (severity === "HIGH") {
        return "MAJOR";
    }
    if (severity === "WARNING") {
        return "WARNING";
    }
    return "INDETERMINATE";
}

var previousTemperature = latestValue("temperature", null);
var previousHumidity = latestValue("humidity", null);
var previousSequence = latestValue("sequence", null);
var previousUptime = latestValue("uptime_s", null);
var previousObservedState = latestValue("observed_state", "INIT");
var previousAnomalyType = latestValue("anomaly_type", "NONE");
var previousStuckCount = latestValue("stuck_count", 0);
var previousInvalidCount = latestValue("invalid_count", 0);
var previousRecoveryCount = latestValue("recovery_count", 0);
var previousActuatorMismatchCount = latestValue("actuator_mismatch_count", 0);

var currentTs = asInteger(metadata.ts, 0);
if (currentTs <= 0) {
    currentTs = Date.now();
}

var temperature = asNumber(msg.temperature, NaN);
var humidity = asNumber(msg.humidity, NaN);
var rssi = asInteger(msg.rssi, -127);
var sequence = asInteger(msg.sequence, -1);
var uptime = asInteger(msg.uptime_s, -1);
var motion = asBoolean(msg.motion, false);
var ledState = asBoolean(msg.led_state, false);
var sensorFlag = asBoolean(msg.sensor_valid, true);

var sensorValid = sensorFlag && isFinite(temperature) && isFinite(humidity) &&
    temperature >= -40 && temperature <= 80 && humidity >= 0 && humidity <= 100;

var tempWarnLow = configNumber("temp_warn_low", 18);
var tempWarnHigh = configNumber("temp_warn_high", 26);
var tempCriticalLow = configNumber("temp_critical_low", 15);
var tempCriticalHigh = configNumber("temp_critical_high", 30);
var humidityWarnLow = configNumber("humidity_warn_low", 55);
var humidityWarnHigh = configNumber("humidity_warn_high", 75);
var humidityCriticalLow = configNumber("humidity_critical_low", 45);
var humidityCriticalHigh = configNumber("humidity_critical_high", 85);
var temperatureRateLimit = configNumber("temperature_rate_cpm", 2);
var humidityRateLimit = configNumber("humidity_rate_ppm", 10);
var stuckEpsilon = configNumber("stuck_epsilon", 0.01);
var stuckSamples = asInteger(metadata.ss_stuck_samples, 12);
var recoveryWindows = asInteger(metadata.ss_recovery_clean_windows, 3);
var actuatorMismatchSamples = asInteger(metadata.ss_actuator_mismatch_samples, 3);
var weakRssiWarning = asInteger(metadata.ss_weak_rssi_warning, -80);
var weakRssiCritical = asInteger(metadata.ss_weak_rssi_critical, -90);
var expectedState = metadata.ss_expected_state || "NORMAL";
var securityMode = metadata.ss_security_mode || "DISARMED";
var expectedLedState = asBoolean(metadata.ss_expected_led_state, ledState);

var candidates = [];
var invalidCount = sensorValid ? 0 : asInteger(previousInvalidCount.value, 0) + 1;
if (!sensorValid && invalidCount >= 3) {
    addCandidate(candidates, "INVALID_SENSOR", 60, {
        invalid_count: invalidCount,
        temperature: msg.temperature,
        humidity: msg.humidity
    });
}

if (sensorValid) {
    if (temperature < tempCriticalLow) {
        addCandidate(candidates, "LOW_TEMPERATURE", 90, { value: temperature, threshold: tempCriticalLow });
    } else if (temperature > tempCriticalHigh) {
        addCandidate(candidates, "HIGH_TEMPERATURE", 90, { value: temperature, threshold: tempCriticalHigh });
    } else if (temperature < tempWarnLow) {
        addCandidate(candidates, "LOW_TEMPERATURE", 40, { value: temperature, threshold: tempWarnLow });
    } else if (temperature > tempWarnHigh) {
        addCandidate(candidates, "HIGH_TEMPERATURE", 40, { value: temperature, threshold: tempWarnHigh });
    }

    if (humidity < humidityCriticalLow) {
        addCandidate(candidates, "LOW_HUMIDITY", 90, { value: humidity, threshold: humidityCriticalLow });
    } else if (humidity > humidityCriticalHigh) {
        addCandidate(candidates, "HIGH_HUMIDITY", 90, { value: humidity, threshold: humidityCriticalHigh });
    } else if (humidity < humidityWarnLow) {
        addCandidate(candidates, "LOW_HUMIDITY", 40, { value: humidity, threshold: humidityWarnLow });
    } else if (humidity > humidityWarnHigh) {
        addCandidate(candidates, "HIGH_HUMIDITY", 40, { value: humidity, threshold: humidityWarnHigh });
    }
}

var temperatureRate = 0;
if (sensorValid && previousTemperature.present && previousTemperature.value !== null) {
    var previousTempNumber = asNumber(previousTemperature.value, temperature);
    var tempDeltaMs = previousTemperature.ts > 0 ? currentTs - previousTemperature.ts : 0;
    if (tempDeltaMs > 0) {
        temperatureRate = Math.abs(temperature - previousTempNumber) / (tempDeltaMs / 60000.0);
        if (temperatureRate > temperatureRateLimit) {
            addCandidate(candidates, "TEMPERATURE_RATE_ANOMALY",
                temperatureRate > temperatureRateLimit * 2 ? 85 : 70,
                { rate_c_per_min: temperatureRate, limit: temperatureRateLimit });
        }
    }
}

var humidityRate = 0;
if (sensorValid && previousHumidity.present && previousHumidity.value !== null) {
    var previousHumidityNumber = asNumber(previousHumidity.value, humidity);
    var humidityDeltaMs = previousHumidity.ts > 0 ? currentTs - previousHumidity.ts : 0;
    if (humidityDeltaMs > 0) {
        humidityRate = Math.abs(humidity - previousHumidityNumber) / (humidityDeltaMs / 60000.0);
        if (humidityRate > humidityRateLimit) {
            addCandidate(candidates, "HUMIDITY_RATE_ANOMALY",
                humidityRate > humidityRateLimit * 2 ? 85 : 70,
                { rate_pct_per_min: humidityRate, limit: humidityRateLimit });
        }
    }
}

var stuckCount = 0;
if (sensorValid && previousTemperature.present && previousHumidity.present) {
    var sameTemperature = Math.abs(temperature - asNumber(previousTemperature.value, temperature)) < stuckEpsilon;
    var sameHumidity = Math.abs(humidity - asNumber(previousHumidity.value, humidity)) < stuckEpsilon;
    stuckCount = sameTemperature && sameHumidity ? asInteger(previousStuckCount.value, 0) + 1 : 0;
    if (stuckCount >= stuckSamples) {
        addCandidate(candidates, "SENSOR_STUCK", 70, {
            samples: stuckCount,
            epsilon: stuckEpsilon,
            temperature: temperature,
            humidity: humidity
        });
    }
}

var restarted = previousUptime.present && uptime >= 0 && uptime < asInteger(previousUptime.value, uptime);
var sequenceGap = 0;
if (restarted) {
    addCandidate(candidates, "DEVICE_RESTART", 65, {
        previous_uptime_s: asInteger(previousUptime.value, 0),
        current_uptime_s: uptime
    });
} else if (previousSequence.present && sequence >= 0) {
    var previousSequenceNumber = asInteger(previousSequence.value, sequence - 1);
    if (sequence === previousSequenceNumber) {
        addCandidate(candidates, "SEQUENCE_GAP", 60, {
            mode: "DUPLICATE",
            previous_sequence: previousSequenceNumber,
            current_sequence: sequence,
            gap: 0
        });
    } else if (sequence < previousSequenceNumber) {
        addCandidate(candidates, "SEQUENCE_GAP", 75, {
            mode: "OUT_OF_ORDER",
            previous_sequence: previousSequenceNumber,
            current_sequence: sequence,
            gap: sequence - previousSequenceNumber - 1
        });
    } else if (sequence > previousSequenceNumber + 1) {
        sequenceGap = sequence - previousSequenceNumber - 1;
        addCandidate(candidates, "SEQUENCE_GAP", Math.min(80, 45 + sequenceGap * 5), {
            mode: "GAP",
            previous_sequence: previousSequenceNumber,
            current_sequence: sequence,
            gap: sequenceGap
        });
    }
}

if (rssi <= weakRssiCritical) {
    addCandidate(candidates, "WEAK_SIGNAL", 80, { rssi: rssi, threshold: weakRssiCritical });
} else if (rssi <= weakRssiWarning) {
    addCandidate(candidates, "WEAK_SIGNAL", 35, { rssi: rssi, threshold: weakRssiWarning });
}

if (String(securityMode).toUpperCase() === "ARMED" && motion) {
    addCandidate(candidates, "UNEXPECTED_MOTION", 70, { security_mode: securityMode, motion: true });
}

var actuatorMismatchCount = ledState !== expectedLedState ?
    asInteger(previousActuatorMismatchCount.value, 0) + 1 : 0;
if (actuatorMismatchCount >= actuatorMismatchSamples) {
    addCandidate(candidates, "ACTUATOR_MISMATCH", 70, {
        expected_led_state: expectedLedState,
        actual_led_state: ledState,
        samples: actuatorMismatchCount
    });
}

var best = { type: "NONE", score: 0, details: {} };
var activeTypes = [];
for (var index = 0; index < candidates.length; index++) {
    activeTypes.push(candidates[index].type);
    if (candidates[index].score > best.score) {
        best = candidates[index];
    }
}

var severity = severityForScore(best.score);
var previousState = String(previousObservedState.value || "INIT");
var recoveryCount = 0;
var observedState;

if (best.type === "DEVICE_RESTART") {
    observedState = "RECOVERY";
    recoveryCount = 0;
} else if (best.score >= 50) {
    observedState = "ANOMALY";
} else if (best.score >= 20) {
    observedState = "WARNING";
} else if (!previousObservedState.present) {
    observedState = "INIT";
} else if (previousState === "OFFLINE" || previousState === "ANOMALY" ||
           previousState === "WARNING" || previousState === "RECOVERY") {
    recoveryCount = asInteger(previousRecoveryCount.value, 0) + 1;
    observedState = recoveryCount >= recoveryWindows ? "NORMAL" : "RECOVERY";
} else {
    observedState = "NORMAL";
}

if (best.score > 0) {
    recoveryCount = 0;
}

var anomaly = best.score > 0;
var healthScore = Math.max(0, 100 - best.score);
var previousType = String(previousAnomalyType.value || "NONE");

msg.last_seen = currentTs;
msg.observed_state = observedState;
msg.expected_state = expectedState;
msg.health_score = healthScore;
msg.anomaly_score = best.score;
msg.anomaly_type = best.type;
msg.anomaly = anomaly;
msg.severity = severity;
msg.online = true;
msg.state_match = observedState === expectedState;
msg.stuck_count = stuckCount;
msg.invalid_count = invalidCount;
msg.recovery_count = recoveryCount;
msg.temperature_rate_cpm = Math.round(temperatureRate * 100) / 100;
msg.humidity_rate_ppm = Math.round(humidityRate * 100) / 100;
msg.sequence_gap = sequenceGap;
msg.expected_led_state = expectedLedState;
msg.actuator_mismatch_count = actuatorMismatchCount;
msg.active_anomalies = JSON.stringify(activeTypes);
msg.anomaly_details = JSON.stringify(best.details);
msg.previous_anomaly_type = previousType;

metadata.prevAlarmType = previousType;
metadata.alarmType = best.type;
metadata.alarmSeverity = alarmSeverity(severity);
metadata.observedState = observedState;

return { msg: msg, metadata: metadata, msgType: msgType };
