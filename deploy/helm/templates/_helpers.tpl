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

{{/*
Effective PVC name for the authoritative /app/data tree.
Uses existingClaim when set, otherwise <release>-data.
*/}}
{{- define "rag-support-assistant.dataClaimName" -}}
{{- if .Values.persistence.data.existingClaim -}}
{{- .Values.persistence.data.existingClaim -}}
{{- else -}}
{{- printf "%s-data" .Release.Name -}}
{{- end -}}
{{- end -}}

{{/*
Effective PVC name for backup snapshots.
Uses existingClaim when set, otherwise <release>-backups.
*/}}
{{- define "rag-support-assistant.backupsClaimName" -}}
{{- if .Values.persistence.backups.existingClaim -}}
{{- .Values.persistence.backups.existingClaim -}}
{{- else -}}
{{- printf "%s-backups" .Release.Name -}}
{{- end -}}
{{- end -}}

{{/*
Effective PVC name for ops reports.
Uses existingClaim when set, otherwise <release>-reports.
*/}}
{{- define "rag-support-assistant.reportsClaimName" -}}
{{- if .Values.persistence.reports.existingClaim -}}
{{- .Values.persistence.reports.existingClaim -}}
{{- else -}}
{{- printf "%s-reports" .Release.Name -}}
{{- end -}}
{{- end -}}
