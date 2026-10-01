var previousType = metadata.prevAlarmType || msg.previous_anomaly_type || "NONE";
var currentType = metadata.alarmType || msg.anomaly_type || "NONE";
return previousType !== "NONE" && previousType !== currentType;

