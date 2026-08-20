# Rack Insight — Argo CD Web UI Hands-on

이 문서는 **Argo CD Web UI에 접속할 수 있는 상태**에서 시작하여 `temocs-bono/rack-insight-pub`을 testbed Kubernetes 클러스터에 배포하는 최소 절차만 정리한다.

현재 repository에는 이미 다음 설정이 반영되어 있다.

- Argo CD source path: `deploy/kubernetes/overlays/testbed`
- Container image registry: `ghcr.io/temocs-bono`
- Image tag: GitHub Actions가 commit SHA 기반으로 자동 갱신
- PostgreSQL StorageClass: `local-path`
- Ingress host: `rack-insight.testbed.local`

따라서 이 문서에서는 위 항목을 사용자가 다시 수정하지 않는다.

---

## 1. 구축 순서

전체 순서는 아래와 같다.

```text
1. local-path-provisioner 설치
2. rack-insight namespace 생성
3. rack-insight-secrets를 로컬 YAML로 생성/적용
4. Argo CD에서 rack-insight Application 생성
5. Sync
6. Pod/PVC 상태 확인
```

> `rack-insight-secrets`는 Git에 commit하지 않고 서버에서 별도로 관리한다.

---

## 2. Local Path Provisioner 설치

Rack Insight의 PostgreSQL은 testbed overlay에서 `local-path` StorageClass를 사용하도록 이미 설정되어 있다.

따라서 Rack Insight를 Sync하기 전에 `local-path` StorageClass가 먼저 존재해야 한다.

### 2.1 Argo CD에서 Application 생성

Argo CD Web UI에서:

```text
Applications
-> NEW APP
```

### GENERAL

```text
Application Name : local-path-provisioner
Project Name     : default
Sync Policy      : Manual
```

### SOURCE

```text
Repository URL : https://github.com/rancher/local-path-provisioner.git
Revision       : v0.0.36
Path           : deploy
```

### KUSTOMIZE

별도 값을 입력하지 않는다.

### DESTINATION

```text
Cluster URL : https://kubernetes.default.svc
Namespace   : local-path-storage
```

`CREATE` 후 `SYNC -> SYNCHRONIZE` 한다.

### 2.2 확인

```bash
kubectl get storageclass
```

다음 StorageClass가 보이면 된다.

```text
local-path
```

---

## 3. Rack Insight Secret 생성

Rack Insight runtime Secret은 Argo CD/Git에서 관리하지 않는다.

서버에서 별도 YAML 파일로 생성해서 Kubernetes에 직접 적용한다.

### 3.1 Namespace 생성

Secret을 먼저 적용할 수 있도록 namespace를 생성한다.

```bash
kubectl create namespace rack-insight
```

이미 존재하는 경우 에러가 나도 문제없다.

---

### 3.2 Secret 파일 생성

Repository를 master 서버에 clone해 두었다면 example 파일을 복사하는 것이 가장 간단하다.

Repository root에서:

```bash
cp deploy/kubernetes/base/secrets/secret.example.yaml /root/rack-insight-secret.yaml
chmod 600 /root/rack-insight-secret.yaml
```

현재 example 파일의 기본 testbed 값은 다음과 같다.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: rack-insight-secrets
  namespace: rack-insight
  labels:
    app.kubernetes.io/part-of: rack-insight
type: Opaque
stringData:
  JWT_SECRET_KEY: "change-me-in-production"
  ENCRYPTION_KEY: "0RPYS0nOu5f5xkbXi3wYlLYasNci4RMOtayEqUKmyNI="
  DEFAULT_ADMIN_PASSWORD: "admin123!"
  DATABASE_URL: "postgresql+asyncpg://rackinsight:rackinsight@postgres:5432/rackinsight"
  POSTGRES_PASSWORD: "rackinsight"
```

testbed에서 빠르게 기동할 때는 위 기본값으로도 동작한다.

실제 운영 환경에서는 반드시 값을 변경한다.

필요하면 새 값을 생성할 수 있다.

```bash
openssl rand -hex 32
```

`JWT_SECRET_KEY` 생성용이다.

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`ENCRYPTION_KEY` 생성용이다.

`POSTGRES_PASSWORD`를 변경하는 경우 `DATABASE_URL` 안의 PostgreSQL password도 반드시 같은 값으로 맞춘다.

예:

```text
POSTGRES_PASSWORD=my-db-password
```

이면:

```text
DATABASE_URL=postgresql+asyncpg://rackinsight:my-db-password@postgres:5432/rackinsight
```

이어야 한다.

---

### 3.3 Secret 적용

```bash
kubectl apply -f /root/rack-insight-secret.yaml
```

확인:

```bash
kubectl get secret rack-insight-secrets -n rack-insight
```

`rack-insight-secrets`가 보이면 완료다.

> `/root/rack-insight-secret.yaml`은 평문 Secret이므로 Git에 추가하지 않는다.

---

## 4. Rack Insight Application 생성

Argo CD Web UI에서:

```text
Applications
-> NEW APP
```

### 4.1 GENERAL

```text
Application Name : rack-insight
Project Name     : default
Sync Policy      : Manual
```

처음 구축할 때는 Manual Sync를 권장한다.

---

### 4.2 SOURCE

```text
Repository URL : https://github.com/temocs-bono/rack-insight-pub.git
Revision       : main
Path           : deploy/kubernetes/overlays/testbed
```

---

### 4.3 KUSTOMIZE

Argo CD Web UI의 Kustomize override 항목은 모두 비워둔다.

```text
Name Prefix        : 비움
Name Suffix        : 비움
Images             : 비움
Replicas           : 비움
Common Labels      : 비움
Common Annotations : 비움
Namespace          : 비움
Kustomize Version  : 기본값
```

실제 Kustomize 설정은 repository의 다음 파일이 관리한다.

```text
deploy/kubernetes/overlays/testbed/kustomization.yaml
```

Argo CD UI에서 image나 storage 설정을 다시 override하지 않는다.

---

### 4.4 DESTINATION

```text
Cluster URL : https://kubernetes.default.svc
Namespace   : rack-insight
```

입력 후 `CREATE` 한다.

---

## 5. Sync

Application을 생성한 후:

```text
rack-insight
-> SYNC
-> SYNCHRONIZE
```

한다.

현재 repository의 testbed overlay에는 이미 다음이 반영되어 있다.

```text
GHCR
ghcr.io/temocs-bono/rack-insight-*

PostgreSQL StorageClass
local-path
```

따라서 별도의 Kustomize 수정은 필요 없다.

---

## 6. 최초 배포 확인

Sync 후 다음 명령 하나로 전체 상태를 먼저 본다.

```bash
kubectl get all -n rack-insight
```

최종적으로 아래 Pod들이 모두 `Running`이어야 한다.

```text
backend          1/1 Running
example-plugin   1/1 Running
frontend         1/1 Running
postgres-0       1/1 Running
redis            1/1 Running
```

PostgreSQL PVC도 한 번 확인한다.

```bash
kubectl get pvc -n rack-insight
```

정상 상태:

```text
data-postgres-0   Bound   ...   local-path
```

Argo CD Web UI에서는 최종적으로:

```text
SYNC STATUS   Synced
HEALTH STATUS Healthy
```

를 확인한다.

---

## 7. 문제 발생 시 최소 확인

### ImagePullBackOff

먼저:

```bash
kubectl describe pod <pod-name> -n rack-insight
```

GHCR 관련 `401 Unauthorized`가 나오면 GitHub의 다음 package들이 **Public**인지 확인한다.

```text
rack-insight-backend
rack-insight-frontend
rack-insight-plugin-example
```

GitHub repository가 Public이어도 GHCR package visibility는 별도다.

---

### postgres-0 Pending

```bash
kubectl get storageclass
kubectl get pvc -n rack-insight
```

`local-path`가 없으면 `local-path-provisioner` Application부터 확인한다.

---

### postgres-0 CreateContainerConfigError

```bash
kubectl describe pod postgres-0 -n rack-insight
```

다음 에러라면 Secret이 적용되지 않은 것이다.

```text
secret "rack-insight-secrets" not found
```

다시 적용한다.

```bash
kubectl apply -f /root/rack-insight-secret.yaml
```

---

### backend Init:0/1

backend는 PostgreSQL이 준비될 때까지 initContainer에서 대기한다.

따라서 먼저 `postgres-0`가 `Running`인지 확인한다.

---

## 8. GitHub Actions 설정이 필요한 경우

현재 `temocs-bono/rack-insight-pub`을 그대로 배포하는 것만으로는 이 항목을 다시 설정할 필요가 없다.

다만 repository를 새로 fork하거나 다른 GitHub account/registry에서 CI/CD를 구성하는 경우 다음 값이 필요하다.

### Actions Variable

```text
REGISTRY = ghcr.io/<OWNER>
```

### Actions Secrets

```text
REGISTRY_USERNAME = <GitHub username>
REGISTRY_PASSWORD = <GHCR write:packages 권한이 있는 PAT>
```

`main`에 push되면 GitHub Actions가 이미지를 build/push하고 testbed의 image SHA tag를 자동으로 갱신한다.

---

## 9. 관리 범위

현재 testbed 기준 관리 방식은 다음과 같다.

```text
Git / Argo CD
- Deployment
- StatefulSet
- Service
- ConfigMap
- Ingress
- Kustomize overlay
- Container image reference
- PostgreSQL StorageClass 설정

서버 로컬
- /root/rack-insight-secret.yaml
- Kubernetes Secret: rack-insight-secrets
```

Secret 파일은 백업 및 권한 관리에 주의하고 Git에는 commit하지 않는다.

---

## 완료 기준

다음 세 가지만 확인되면 testbed 배포 완료다.

```text
1. Argo CD
   rack-insight = Synced / Healthy

2. Kubernetes
   backend / frontend / example-plugin / postgres / redis = Running

3. Storage
   data-postgres-0 = Bound (local-path)
```
