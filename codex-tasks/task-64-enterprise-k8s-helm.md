# Task 64 — DEPLOY-1: Kubernetes Helm chart

## Goal
Создать Helm chart для deployment в Kubernetes.
Компоненты: app (HPA), PostgreSQL (StatefulSet), Redis, Ollama (GPU node).

## Files to create
- `deploy/helm/Chart.yaml`
- `deploy/helm/values.yaml`
- `deploy/helm/templates/deployment.yaml`
- `deploy/helm/templates/service.yaml`
- `deploy/helm/templates/configmap.yaml`
- `deploy/helm/templates/hpa.yaml`
- `deploy/helm/templates/ingress.yaml`

---

## 1. deploy/helm/Chart.yaml

```yaml
apiVersion: v2
name: rag-support-assistant
description: RAG Support Assistant — AI-powered knowledge base Q&A
version: 0.1.0
appVersion: "0.3.0"
```

---

## 2. deploy/helm/values.yaml

```yaml
replicaCount: 2

image:
  repository: rag-support-assistant
  tag: latest
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: false
  className: nginx
  hosts:
    - host: support.example.com
      paths:
        - path: /
          pathType: Prefix

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 2000m
    memory: 4Gi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 8
  targetCPUUtilizationPercentage: 70

env:
  OLLAMA_BASE_URL: "http://ollama:11434"
  DATABASE_URL: "postgresql://rag:changeme@postgres:5432/rag_assistant"
  REDIS_URL: "redis://redis:6379/0"
  REQUIRE_OLLAMA: "true"
  RAG_SEMANTIC_CHUNKING: "true"

postgresql:
  enabled: true
  auth:
    database: rag_assistant
    username: rag
    password: changeme

redis:
  enabled: true

ollama:
  enabled: true
  model: "qwen2.5:7b"
  resources:
    limits:
      nvidia.com/gpu: 1
```

---

## 3. deploy/helm/templates/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-app
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: {{ .Release.Name }}-app
  template:
    metadata:
      labels:
        app: {{ .Release.Name }}-app
    spec:
      containers:
        - name: app
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: {{ .Release.Name }}-config
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 15
          livenessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 30
```

---

## 4. deploy/helm/templates/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}-app
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: 8000
  selector:
    app: {{ .Release.Name }}-app
```

---

## 5. deploy/helm/templates/configmap.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Release.Name }}-config
data:
  {{- range $key, $value := .Values.env }}
  {{ $key }}: {{ $value | quote }}
  {{- end }}
```

---

## 6. deploy/helm/templates/hpa.yaml

```yaml
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ .Release.Name }}-app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ .Release.Name }}-app
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
{{- end }}
```

---

## 7. deploy/helm/templates/ingress.yaml

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Release.Name }}-ingress
spec:
  ingressClassName: {{ .Values.ingress.className }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ $.Release.Name }}-app
                port:
                  number: {{ $.Values.service.port }}
          {{- end }}
    {{- end }}
{{- end }}
```

---

## CONSTRAINTS
- Только создать файлы в `deploy/helm/`
- `helm lint deploy/helm/` — проходит (если helm установлен)
- `helm template test deploy/helm/` — генерирует валидный YAML
- Не ломать существующий docker-compose
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] Helm chart в `deploy/helm/`
- [ ] `Chart.yaml` + `values.yaml` + 5 template files
- [ ] Readiness/liveness probes на /api/health
- [ ] HPA: 2-8 pods по CPU
- [ ] Ingress optional (disabled by default)
- [ ] `helm lint deploy/helm/` — 0 errors (если helm доступен)
