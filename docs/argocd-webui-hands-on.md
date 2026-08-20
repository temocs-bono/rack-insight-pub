# Rack Insight — Argo CD Web UI Hands-on Deployment Guide

> **목적**  
> 이 문서는 **Argo CD Web UI에 접속할 수 있는 상태**에서 시작하여,  
> `temocs-bono/rack-insight-pub` 저장소를 Kubernetes testbed 클러스터에 GitOps 방식으로 배포하는 전체 과정을 실제 Hands-on 순서로 정리한다.
>
> 이 문서의 범위에는 다음이 포함된다.
>
> - Argo CD Application 생성
> - Kustomize 설정
> - GitHub Actions + GHCR 이미지 빌드/배포
> - GHCR `401 Unauthorized` / `ImagePullBackOff` 해결
> - PostgreSQL PVC `Pending` 문제 확인
> - Local Path Provisioner를 Argo CD로 설치
> - PostgreSQL에 `local-path` StorageClass 적용
> - 최종 Pod / PVC / Argo CD 상태 검증
>
> **시작점:** Argo CD 설치 및 Argo CD Web UI 접속 자체는 완료되어 있다고 가정한다.

---

## 1. 최종 배포 구조

Rack Insight testbed의 목표 흐름은 다음과 같다.

```text
Developer
   |
   v
GitHub main
   |
   +--> GitHub Actions
   |      |
   |      +--> Build & Test
   |      +--> Docker image build
   |      +--> GHCR push
   |      +--> testbed kustomization image tag 갱신
   |      +--> GitOps commit to main
   |
   v
Argo CD
   |
   +--> deploy/kubernetes/overlays/testbed
   |
   v
Kubernetes Cluster
   |
   +--> frontend
   +--> backend
   +--> example-plugin
   +--> redis
   +--> postgres
```

이미지에는 `latest` 대신 Git commit 기반 immutable tag를 사용한다.

예:

```text
ghcr.io/temocs-bono/rack-insight-backend:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-frontend:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-plugin-example:sha-d9e0971
```

---

# Part 1. Rack Insight Application 생성

## 2. Argo CD Web UI에서 Application 생성

Argo CD Web UI에서:

```text
Applications
  -> NEW APP
```

을 선택한다.

### 2.1 GENERAL

다음과 같이 입력한다.

| 항목 | 값 |
|---|---|
| Application Name | `rack-insight` |
| Project Name | `default` |
| Sync Policy | 처음 구축 시 `Manual` 권장 |

처음부터 Auto Sync를 켜지 않는 이유는 초기 구축 시 Registry, StorageClass, Secret 등의 prerequisite를 먼저 확인하기 위함이다.

---

## 3. SOURCE 설정

다음 값을 입력한다.

```text
Repository URL
https://github.com/temocs-bono/rack-insight-pub.git

Revision
main

Path
deploy/kubernetes/overlays/testbed
```

Argo CD가 실제로 감시할 위치는 다음 파일이다.

```text
deploy/kubernetes/overlays/testbed/kustomization.yaml
```

즉 Argo CD가 repository root 전체를 직접 배포하는 것이 아니라 testbed overlay를 Kustomize source로 사용한다.

---

## 4. KUSTOMIZE 항목 설정

Argo CD Web UI의 `KUSTOMIZE` 영역에는 여러 override 항목이 있지만, Rack Insight에서는 **기본적으로 모두 비워둔다.**

```text
Name Prefix        [비움]
Name Suffix        [비움]
Images             [비움]
Replicas           [비움]
Common Labels      [비움]
Common Annotations [비움]
Namespace          [비움]
Kustomize Version  [기본값]
```

### 왜 비워두는가?

환경별 Kustomize 설정은 Git의 다음 파일이 source of truth이기 때문이다.

```text
deploy/kubernetes/overlays/testbed/kustomization.yaml
```

예를 들어 이미지와 Ingress host가 이미 Git에 정의되어 있다.

```yaml
images:
  - name: rack-insight-backend
    newName: REGISTRY_PLACEHOLDER/rack-insight-backend
    newTag: "1.4.0"

  - name: rack-insight-frontend
    newName: REGISTRY_PLACEHOLDER/rack-insight-frontend
    newTag: "1.4.0"

  - name: rack-insight-plugin-example
    newName: REGISTRY_PLACEHOLDER/rack-insight-plugin-example
    newTag: "1.4.0"
```

Argo CD UI의 `Images` 등에 같은 값을 또 넣으면 Git desired state와 Argo CD-side override가 섞이므로 특별한 이유가 없는 한 사용하지 않는다.

---

## 5. DESTINATION 설정

```text
Cluster URL
https://kubernetes.default.svc

Namespace
rack-insight
```

주의:

```text
KUSTOMIZE -> Namespace
```

와

```text
DESTINATION -> Namespace
```

는 다른 설정이다.

이 Hands-on에서는:

```text
KUSTOMIZE Namespace = 비움
DESTINATION Namespace = rack-insight
```

으로 설정한다.

입력 후:

```text
CREATE
```

를 누른다.

초기 prerequisite가 아직 준비되지 않았다면 바로 `SYNC`하지 않는다.

---

# Part 2. GitHub Actions와 Container Image 준비

## 6. Rack Insight CI/CD 동작 이해

repository의 workflow:

```text
.github/workflows/ci.yml
```

은 `main`에 push가 발생하면 다음 작업을 수행한다.

```text
main push
   |
   v
Backend tests
Frontend build
   |
   v
Docker image build
   |
   v
Container Registry push
   |
   v
kustomize edit set image
   |
   v
deploy/kubernetes/overlays/testbed/kustomization.yaml 수정
   |
   v
GitOps commit + push
```

생성되는 이미지 이름은 다음과 같다.

```text
${REGISTRY}/rack-insight-backend:${TAG}
${REGISTRY}/rack-insight-frontend:${TAG}
${REGISTRY}/rack-insight-plugin-example:${TAG}
```

이번 Hands-on에서는 GHCR을 사용한다.

```text
REGISTRY = ghcr.io/temocs-bono
```

---

## 7. GitHub Actions Variable 설정

GitHub repository에서:

```text
Settings
  -> Secrets and variables
  -> Actions
  -> Variables
```

로 이동한다.

`New repository variable`을 선택한다.

```text
Name
REGISTRY

Value
ghcr.io/temocs-bono
```

최종적으로:

```text
REGISTRY = ghcr.io/temocs-bono
```

가 있어야 한다.

---

# Part 3. GHCR push용 Secret 설정

## 8. GitHub Personal Access Token 생성

현재 repository workflow는 다음 Secrets를 사용한다.

```text
REGISTRY_USERNAME
REGISTRY_PASSWORD
```

따라서 현재 workflow를 그대로 사용할 경우 GHCR push 권한이 있는 PAT가 필요하다.

GitHub 사용자 설정으로 이동한다.

```text
Profile
  -> Settings
  -> Developer settings
  -> Personal access tokens
  -> Tokens (classic)
  -> Generate new token
  -> Generate new token (classic)
```

예시 설정:

```text
Note
rack-insight-ghcr

Expiration
테스트 환경 정책에 맞게 설정

Scope
write:packages
```

생성된 token 예:

```text
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> PAT는 Git repository에 절대 commit하지 않는다.

---

## 9. GitHub Actions Secrets 생성

repository:

```text
Settings
  -> Secrets and variables
  -> Actions
  -> Secrets
```

로 이동한다.

### Secret 1

```text
Name
REGISTRY_USERNAME

Secret
temocs-bono
```

### Secret 2

```text
Name
REGISTRY_PASSWORD

Secret
<앞에서 생성한 GitHub PAT>
```

최종 구성:

```text
Variables

REGISTRY
= ghcr.io/temocs-bono
```

```text
Secrets

REGISTRY_USERNAME
= temocs-bono

REGISTRY_PASSWORD
= <GitHub PAT>
```

---

# Part 4. GitHub Actions 실행

## 10. main push 발생시키기

workflow는 `main` push를 trigger로 실행된다.

따라서 README 또는 문서 등에 정상적인 변경을 하나 commit한다.

GitHub Web을 사용한다면:

```text
README.md
 -> Edit
 -> 변경
 -> Commit changes
 -> main
```

또는 로컬 Git을 사용한다.

```bash
git add .
git commit -m "docs: update deployment guide"
git push origin main
```

---

## 11. GitHub Actions 확인

GitHub:

```text
Actions
  -> CI
```

로 이동한다.

정상적인 workflow 흐름:

```text
Build & Test
  |
  +-- Backend tests
  +-- Frontend build

Build, Push & GitOps update
  |
  +-- Compute image tag
  +-- Log in to the container registry
  +-- Build & push images
  +-- Update testbed overlay image tags
  +-- Commit & push GitOps change
```

성공하면 testbed `kustomization.yaml`이 CI에 의해 자동 변경된다.

변경 전 예:

```yaml
newName: REGISTRY_PLACEHOLDER/rack-insight-frontend
newTag: "1.4.0"
```

변경 후 예:

```yaml
newName: ghcr.io/temocs-bono/rack-insight-frontend
newTag: sha-d9e0971
```

backend와 plugin image도 같은 SHA tag를 사용한다.

---

# Part 5. Argo CD 최초 Sync

## 12. Argo CD Refresh

GitHub Actions가 성공한 후 Argo CD에서:

```text
Applications
  -> rack-insight
  -> Refresh
```

를 수행한다.

정상적으로 Git 변경이 감지되면:

```text
OutOfSync
```

상태가 나타날 수 있다.

그 다음:

```text
SYNC
 -> SYNCHRONIZE
```

를 실행한다.

---

## 13. Kubernetes 상태 확인

master node에서:

```bash
kubectl get all -n rack-insight
```

초기 배포에서는 모든 Pod가 즉시 Running이 아닐 수 있다.

이번 구축 과정에서는 처음 다음과 같은 상태가 발생했다.

```text
backend          Init:0/1
example-plugin   ErrImagePull
frontend         ImagePullBackOff
postgres-0       Pending
redis            Running
```

여기서 중요한 점은 한 번에 모든 문제를 고치려고 하지 않고 **Pod Events를 기준으로 각각 원인을 분리하는 것**이다.

---

# Part 6. ImagePullBackOff / GHCR 401 해결

## 14. Pod Events 확인

예:

```bash
kubectl describe pod <frontend-pod-name> -n rack-insight
```

```bash
kubectl describe pod <example-plugin-pod-name> -n rack-insight
```

이번 환경에서 실제 원인은 다음과 같은 GHCR 인증 오류였다.

```text
failed to authorize
failed to fetch anonymous token
401 Unauthorized
```

실제 배포 image reference 자체는 정상적인 SHA tag였다.

```text
ghcr.io/temocs-bono/rack-insight-frontend:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-plugin-example:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-backend:sha-d9e0971
```

따라서 문제는 image name이나 tag가 아니라 **GHCR package visibility**였다.

---

## 15. GHCR package를 Public으로 변경

이 repository는 public project이고 testbed cluster에서 인증 Secret 없이 이미지를 pull하도록 구성할 수 있다.

GitHub에서 자신의 Packages로 이동한다.

다음 세 package를 각각 확인한다.

```text
rack-insight-backend
rack-insight-frontend
rack-insight-plugin-example
```

각 Package Settings에서 visibility를:

```text
Private
  ->
Public
```

으로 변경한다.

최종 목표:

```text
rack-insight-backend         Public
rack-insight-frontend        Public
rack-insight-plugin-example  Public
```

중요:

> GitHub repository가 Public이라고 해서 GHCR package가 자동으로 Public인 것은 아니다.

Package가 Public이 되면 Kubernetes는 별도의 `imagePullSecret` 없이 anonymous pull을 할 수 있다.

---

## 16. 이미지 재확인

Kubernetes가 자동으로 pull을 재시도한다.

상태 확인:

```bash
kubectl get pods -n rack-insight -w
```

필요하면 현재 Deployment image도 확인한다.

```bash
kubectl get deployment frontend \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

```bash
kubectl get deployment example-plugin \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

```bash
kubectl get deployment backend \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

정상 예:

```text
ghcr.io/temocs-bono/rack-insight-frontend:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-plugin-example:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-backend:sha-d9e0971
```

이번 구축에서는 visibility 변경 후:

```text
example-plugin   1/1 Running
frontend         1/1 Running
redis            1/1 Running
```

까지 정상화되었다.

---

# Part 7. PostgreSQL Pending 문제 분석

## 17. PostgreSQL 상태 확인

다음 상태가 남을 수 있다.

```text
postgres-0   0/1 Pending
backend      0/1 Init:0/1
```

Postgres 확인:

```bash
kubectl describe pod postgres-0 -n rack-insight
```

이번 환경에서는 다음 이벤트가 확인되었다.

```text
0/3 nodes are available:
pod has unbound immediate PersistentVolumeClaims
```

PVC 확인:

```bash
kubectl get pvc -n rack-insight
```

결과:

```text
NAME              STATUS
data-postgres-0   Pending
```

StorageClass 확인:

```bash
kubectl get storageclass
```

결과:

```text
No resources found
```

즉 문제는 명확하다.

```text
Postgres
   |
   v
8Gi RWO PVC 요청
   |
   v
PVC 생성
   |
   X
StorageClass / Dynamic Provisioner 없음
   |
   v
PVC Pending
   |
   v
Postgres Pending
```

---

## 18. Backend가 Init 상태인 이유

backend에는 PostgreSQL을 기다리는 initContainer가 있다.

동작은 다음과 같다.

```sh
until pg_isready -h postgres -p 5432; do
  echo waiting for postgres
  sleep 2
done
```

따라서:

```text
postgres Pending
    ->
postgres Service에 Ready DB 없음
    ->
backend initContainer 대기
    ->
backend Init:0/1
```

이다.

즉 backend를 직접 수정할 문제가 아니다.

Postgres storage가 해결되면 backend가 다음 단계로 진행한다.

---

# Part 8. Local Path Provisioner를 Argo CD로 구축

## 19. 왜 수동 kubectl apply를 사용하지 않는가?

Argo CD를 사용하는 환경에서는 가능하면 infrastructure component도 GitOps 관리 대상으로 두는 것이 관리상 유리하다.

따라서 다음 명령으로 직접 설치하는 대신:

```text
kubectl apply -f ...
```

Argo CD에서 **별도의 Application**으로 Local Path Provisioner를 생성한다.

Rack Insight Application과 infrastructure Application을 분리하면 책임 범위가 명확해진다.

```text
Argo CD

├── rack-insight
│    └── 애플리케이션 workload
│
└── local-path-provisioner
     └── cluster storage infrastructure
```

---

## 20. Local Path Provisioner Application 생성

Argo CD Web UI:

```text
Applications
 -> NEW APP
```

### GENERAL

```text
Application Name
local-path-provisioner

Project
default

Sync Policy
Manual
```

### SOURCE

```text
Repository URL
https://github.com/rancher/local-path-provisioner.git

Revision
v0.0.36

Path
deploy
```

### KUSTOMIZE

특별한 override는 넣지 않는다.

```text
Name Prefix        [비움]
Name Suffix        [비움]
Images             [비움]
Replicas           [비움]
Namespace          [비움]
```

### DESTINATION

```text
Cluster
https://kubernetes.default.svc

Namespace
local-path-storage
```

그 다음:

```text
CREATE
 -> SYNC
 -> SYNCHRONIZE
```

한다.

Local Path Provisioner의 stable `v0.0.36` 구성은 기본적으로:

```text
Namespace
local-path-storage

StorageClass
local-path

Provisioner
rancher.io/local-path

Volume Binding Mode
WaitForFirstConsumer
```

를 사용한다.

기본 node storage path는 다음이다.

```text
/opt/local-path-provisioner
```

> Local Path Provisioner는 노드 로컬 스토리지다.  
> 일반적인 공유 스토리지/NFS/Ceph와 동일한 HA 특성을 제공하는 것으로 오해하면 안 된다.  
> testbed/home-lab 용도로는 간단하지만, production storage 정책은 별도로 설계해야 한다.

---

## 21. Local Path Provisioner 검증

```bash
kubectl get pods -n local-path-storage
```

정상 예:

```text
local-path-provisioner-xxxxxxxxxx-xxxxx   1/1 Running
```

StorageClass 확인:

```bash
kubectl get storageclass
```

정상 예:

```text
NAME         PROVISIONER
local-path   rancher.io/local-path
```

이 상태가 확인되어야 다음 단계로 진행한다.

---

# Part 9. Postgres가 local-path StorageClass를 사용하도록 Git 수정

## 22. 현재 PostgreSQL PVC 정의

Rack Insight PostgreSQL은 StatefulSet의 `volumeClaimTemplates`에서 PVC를 생성한다.

요청 조건:

```text
Access Mode : ReadWriteOnce
Size        : 8Gi
```

base manifest에서는 `storageClassName`을 특정 환경에 고정하지 않는다.

이것은 의도된 구조다.

```text
base
  -> 환경 독립적인 설정

overlay/testbed
  -> testbed 환경 특화 설정
```

따라서 `local-path`는 base가 아니라 **testbed overlay**에서 지정한다.

---

## 23. testbed kustomization 수정

수정 파일:

```text
deploy/kubernetes/overlays/testbed/kustomization.yaml
```

기존 `patches:` 아래에 Postgres patch를 추가한다.

예:

```yaml
patches:
  - target:
      kind: Ingress
      name: rack-insight
    patch: |
      - op: replace
        path: /spec/rules/0/host
        value: rack-insight.testbed.local

  - target:
      kind: StatefulSet
      name: postgres
    patch: |-
      - op: add
        path: /spec/volumeClaimTemplates/0/spec/storageClassName
        value: local-path
```

핵심 부분은 다음이다.

```yaml
- op: add
  path: /spec/volumeClaimTemplates/0/spec/storageClassName
  value: local-path
```

GitHub Web에서 수정했다면:

```text
Commit changes
 -> main
```

을 수행한다.

로컬에서 수정했다면:

```bash
git add deploy/kubernetes/overlays/testbed/kustomization.yaml
git commit -m "deploy: use local-path storage for testbed postgres"
git push origin main
```

---

# Part 10. 기존 Pending PVC 처리

## 24. 왜 기존 PVC를 처리해야 하는가?

현재 이미 다음 PVC가 만들어져 있다.

```text
data-postgres-0
```

그러나 이 PVC는 StorageClass가 없던 시점에 생성되어:

```text
STATUS = Pending
STORAGECLASS = <unset>
```

상태다.

Git에서 StatefulSet의 `volumeClaimTemplates`를 변경했다고 해서 이미 생성된 PVC의 storageClass가 자동으로 원하는 값으로 재작성되는 것으로 가정하면 안 된다.

이번 구축은 **최초 배포 중이며 Postgres가 한 번도 정상 기동하지 못한 상태**이므로 기존 Pending PVC에 실제 DB 데이터가 없다.

따라서 이 초기 구축 시점에는 기존 Pending PVC를 삭제한 후 새 desired state 기준으로 다시 생성시킨다.

먼저 반드시 확인한다.

```bash
kubectl get pvc -n rack-insight
```

정확히 다음과 같이 `Pending`이고 실제 DB가 사용되지 않았음을 확인한 후:

```bash
kubectl delete pvc data-postgres-0 -n rack-insight
```

을 수행한다.

> **주의:**  
> 운영 중이거나 데이터가 기록된 PVC에 이 절차를 사용하면 안 된다.  
> 데이터가 있는 PersistentVolume/PVC 변경은 별도의 migration/backup/restore 절차가 필요하다.

---

# Part 11. Rack Insight 재동기화

## 25. Argo CD Refresh

Argo CD에서:

```text
Applications
 -> rack-insight
 -> Refresh
```

Git의 변경을 감지하면:

```text
OutOfSync
```

상태를 확인한다.

그 다음:

```text
SYNC
 -> SYNCHRONIZE
```

한다.

---

## 26. PVC 상태 확인

```bash
kubectl get pvc -n rack-insight
```

목표:

```text
NAME              STATUS   STORAGECLASS
data-postgres-0   Bound    local-path
```

PV도 확인할 수 있다.

```bash
kubectl get pv
```

---

## 27. PostgreSQL 상태 확인

```bash
kubectl get pods -n rack-insight -w
```

정상적인 진행 예:

```text
postgres-0
Pending
 -> ContainerCreating
 -> Running
```

필요하면:

```bash
kubectl describe pod postgres-0 -n rack-insight
```

```bash
kubectl logs postgres-0 -n rack-insight
```

로 확인한다.

---

## 28. Backend 상태 확인

Postgres가 Ready가 되면 backend의 `wait-for-postgres` initContainer가 통과해야 한다.

확인:

```bash
kubectl get pods -n rack-insight
```

최종 목표:

```text
backend          1/1 Running
example-plugin   1/1 Running
frontend         1/1 Running
postgres-0       1/1 Running
redis            1/1 Running
```

---

# Part 12. 최종 검증

## 29. 전체 Kubernetes resource 확인

```bash
kubectl get all -n rack-insight
```

추가로:

```bash
kubectl get pvc -n rack-insight
kubectl get pv
kubectl get storageclass
kubectl get ingress -n rack-insight
```

을 확인한다.

---

## 30. Deployment image 검증

```bash
kubectl get deployment backend \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

```bash
kubectl get deployment frontend \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

```bash
kubectl get deployment example-plugin \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

모두 같은 Git commit 기반 SHA tag를 사용하는지 확인한다.

예:

```text
ghcr.io/temocs-bono/rack-insight-backend:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-frontend:sha-d9e0971
ghcr.io/temocs-bono/rack-insight-plugin-example:sha-d9e0971
```

---

## 31. Argo CD 최종 상태

Argo CD Web UI의 `rack-insight` Application에서 최종적으로:

```text
Sync Status
Synced

Health Status
Healthy
```

를 목표로 한다.

Local Path Provisioner Application 역시:

```text
Synced
Healthy
```

상태인지 확인한다.

---

# Part 13. Troubleshooting Cheat Sheet

## 32. ImagePullBackOff

확인:

```bash
kubectl describe pod <pod> -n rack-insight
```

### `401 Unauthorized`

예:

```text
failed to fetch anonymous token
401 Unauthorized
```

확인할 것:

1. GHCR package가 존재하는가
2. image tag가 존재하는가
3. GitHub repository Public 여부와 별개로 GHCR Package가 Public인가

현재 public testbed 전략에서는 세 GHCR package를 Public으로 설정한다.

---

## 33. Postgres Pending

확인:

```bash
kubectl describe pod postgres-0 -n rack-insight
kubectl get pvc -n rack-insight
kubectl get storageclass
```

다음 조합이면 Storage 문제다.

```text
postgres-0 = Pending
PVC        = Pending
StorageClass = 없음
```

해결:

```text
local-path-provisioner Argo CD Application 설치
 -> local-path StorageClass 생성
 -> testbed overlay에 storageClassName: local-path
 -> 기존 초기 Pending PVC 정리
 -> rack-insight Sync
```

---

## 34. Backend `Init:0/1`

다음으로 initContainer 확인:

```bash
kubectl describe pod <backend-pod> -n rack-insight
```

`wait-for-postgres`가 실행 중이면 backend image 문제가 아니라 Postgres가 아직 Ready가 아닌 것이다.

Postgres/PVC부터 해결한다.

---

## 35. 현재 image가 무엇인지 확인

```bash
kubectl get deployment backend \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'
```

`REGISTRY_PLACEHOLDER`가 남아 있으면 CI/GitOps image update가 정상 수행되지 않은 것이다.

정상이라면:

```text
ghcr.io/temocs-bono/rack-insight-*:sha-xxxxxxx
```

형태여야 한다.

---

# Part 14. Secret 관리에 대한 중요 주의사항

## 36. 현재 repository의 Secret 정책

현재 Rack Insight Kustomize base는 실제 `rack-insight-secrets` Secret을 의도적으로 resources에 포함하지 않는다.

즉 실제 민감정보를 일반 Git repository에 평문으로 commit하지 않는 것이 현재 repository의 설계다.

필요한 민감값에는 예를 들어 다음이 포함된다.

```text
JWT_SECRET_KEY
ENCRYPTION_KEY
DEFAULT_ADMIN_PASSWORD
DATABASE_URL
POSTGRES_PASSWORD
```

따라서 이 문서에서 다음 두 종류를 구분해야 한다.

### GitHub Actions Secret

CI가 GHCR에 image를 push하기 위한 Secret.

```text
REGISTRY_USERNAME
REGISTRY_PASSWORD
```

이 값들은 GitHub Actions Secrets에 저장된다.

### Kubernetes Application Secret

Rack Insight runtime이 사용하는:

```text
rack-insight-secrets
```

는 별개의 Kubernetes Secret이다.

현재 repository는 실제 runtime secret을 Git에 평문으로 넣지 않도록 구성되어 있다.

---

## 37. 완전한 GitOps Secret 관리로 확장하려면

장기적으로 "Argo CD가 모든 desired state를 관리한다"는 운영 모델을 원한다면 일반 Secret YAML을 public Git에 commit하는 방식이 아니라 다음과 같은 Secret management 방식을 도입하는 것이 적절하다.

예:

```text
Sealed Secrets
External Secrets Operator
SOPS + Argo CD integration
```

이 부분은 현재 Hands-on 범위에서는 별도 구축 대상으로 남긴다.

---

# Part 15. 구축 순서 요약

전체 순서를 다시 정리하면 다음과 같다.

```text
[1] Argo CD Web UI 접속

[2] rack-insight Application 생성
    Repository = rack-insight-pub
    Revision   = main
    Path       = deploy/kubernetes/overlays/testbed
    Destination namespace = rack-insight

[3] Kustomize UI override는 비움

[4] GitHub Actions Variable 설정
    REGISTRY = ghcr.io/temocs-bono

[5] GHCR push용 PAT 생성

[6] GitHub Actions Secrets 설정
    REGISTRY_USERNAME = temocs-bono
    REGISTRY_PASSWORD = PAT

[7] main push

[8] GitHub Actions 성공 확인

[9] kustomization.yaml image가
    ghcr.io/...:sha-xxxx 형태로 변경됐는지 확인

[10] Argo CD rack-insight Refresh / Sync

[11] Pod 상태 확인

[12] ImagePullBackOff + 401이면
     GHCR packages를 Public으로 변경

[13] frontend / example-plugin Running 확인

[14] postgres Pending 확인

[15] kubectl get pvc
     -> data-postgres-0 Pending

[16] kubectl get storageclass
     -> 없음 확인

[17] Argo CD에 local-path-provisioner Application 생성

[18] local-path-provisioner Sync

[19] kubectl get storageclass
     -> local-path 확인

[20] rack-insight testbed kustomization에
     postgres storageClassName: local-path patch 추가

[21] Git commit / push

[22] 최초 구축 중 생성된 기존 Pending PVC 삭제

[23] rack-insight Refresh / Sync

[24] PVC Bound 확인

[25] postgres Running 확인

[26] backend init 통과 확인

[27] 전체 Pod Running 확인

[28] Argo CD Synced + Healthy 확인
```

---

# Appendix A. 주요 파일

```text
.github/workflows/ci.yml
```

CI/CD workflow.

```text
deploy/argocd/application.yaml
```

Rack Insight Argo CD Application 선언 예제.

```text
deploy/kubernetes/base/kustomization.yaml
```

환경 독립 Kubernetes base.

```text
deploy/kubernetes/base/postgres/statefulset.yaml
```

Postgres StatefulSet 및 `8Gi` PVC template.

```text
deploy/kubernetes/overlays/testbed/kustomization.yaml
```

testbed 환경의 실제 Argo CD Kustomize source.

---

# Appendix B. 자주 사용하는 확인 명령

```bash
# 전체 상태
kubectl get all -n rack-insight

# Pod
kubectl get pods -n rack-insight -o wide

# PVC
kubectl get pvc -n rack-insight

# PV
kubectl get pv

# StorageClass
kubectl get storageclass

# Ingress
kubectl get ingress -n rack-insight

# 특정 Pod 상세
kubectl describe pod <pod-name> -n rack-insight

# Backend logs
kubectl logs deploy/backend -n rack-insight

# Postgres logs
kubectl logs postgres-0 -n rack-insight

# Backend init container log
kubectl logs <backend-pod-name> \
  -n rack-insight \
  -c wait-for-postgres

# 실제 backend image
kubectl get deployment backend \
  -n rack-insight \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}'

# local-path provisioner
kubectl get pods -n local-path-storage

# 실시간 Pod 상태
kubectl get pods -n rack-insight -w
```

---

# Appendix C. Testbed와 Production의 차이

이 문서의 `local-path` 구성은 **testbed/home-lab 기준**이다.

Local Path Provisioner는 local node storage를 사용한다.

따라서 production에서는 다음을 별도로 검토해야 한다.

```text
Storage HA
Node failure 시 데이터 복구
Backup / Restore
Snapshot
Reclaim policy
Managed PostgreSQL 사용 여부
NFS / Ceph / CSI storage 사용 여부
Secret management
Registry access policy
Argo CD RBAC
Auto Sync / Prune / Self Heal 정책
```

Rack Insight의 `base`에 특정 StorageClass를 박아 넣지 않고 overlay에서 storage 정책을 결정하는 이유도 이 때문이다.

---

## 완료 기준

아래 조건이 모두 만족되면 testbed 구축 완료로 본다.

```text
GitHub Actions       Success
GHCR Images          Pull 가능
rack-insight         Synced / Healthy
local-path-provisioner Synced / Healthy

frontend             1/1 Running
backend              1/1 Running
example-plugin       1/1 Running
redis                1/1 Running
postgres-0           1/1 Running

data-postgres-0      Bound
StorageClass         local-path
```
