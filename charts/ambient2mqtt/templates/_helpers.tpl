{{- define "ambient2mqtt.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ambient2mqtt.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "ambient2mqtt.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "ambient2mqtt.labels" -}}
app.kubernetes.io/name: {{ include "ambient2mqtt.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "ambient2mqtt.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ambient2mqtt.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "ambient2mqtt.secretName" -}}
{{- if .Values.ambient.create -}}
{{- include "ambient2mqtt.fullname" . -}}
{{- else -}}
{{- required "ambient.existingSecret is required when ambient.create is false" .Values.ambient.existingSecret -}}
{{- end -}}
{{- end -}}
