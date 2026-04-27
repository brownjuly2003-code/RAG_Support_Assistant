{{/*
envFrom block: ConfigMap (public env) + Secret (sensitive credentials).
The Secret name resolves to an external `existingSecret` when provided,
otherwise to the chart-managed `<release>-secrets`.
*/}}
{{- define "rag-support-assistant.envFrom" -}}
- configMapRef:
    name: {{ .Release.Name }}-config
- secretRef:
    name: {{ .Values.secrets.existingSecret | default (printf "%s-secrets" .Release.Name) }}
{{- end -}}

{{/*
Image reference: tag falls back to Chart appVersion so we never publish
`latest` by default.
*/}}
{{- define "rag-support-assistant.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end -}}
