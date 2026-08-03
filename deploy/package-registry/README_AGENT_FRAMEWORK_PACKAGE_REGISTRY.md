# Publicação do `agent_framework` como biblioteca corporativa

Este manual complementa o deployment no OKE com a abordagem correta para o `agent_framework`: ele não é um Deployment Kubernetes. Ele é uma biblioteca Python versionada, publicada em um registry privado e consumida pelos agentes com `pip install`.

## Objetivo

Permitir que aplicações como `agent_template_backend`, `agent_gateway`, `channel_gateway` e outros agentes façam:

```python
from agent_framework import ...
```

sem copiar código manualmente e sem depender de paths locais do monorepo.

## Modelo recomendado

```text
libs/agent_framework
        │
        ├── pyproject.toml
        ├── src/agent_framework
        └── dist/
             ├── agent_framework-<version>-py3-none-any.whl
             └── agent_framework-<version>.tar.gz

Registry privado
        ├── Azure DevOps Artifacts  [recomendado para PyPI privado]
        └── GitHub Release Assets   [alternativa quando o código está no GitHub]

Agentes
        └── pip install agent-framework==<version>
```

## Importante sobre GitHub Packages

GitHub Packages é um serviço de packages, mas no momento ele não oferece um registry Python/PyPI compatível como Azure Artifacts, GitLab Package Registry, Nexus, Artifactory ou PyPI. Por isso, para GitHub foram incluídas duas alternativas práticas:

1. publicar o wheel/sdist em **GitHub Releases**;
2. usar GitHub Actions para publicar em um registry PyPI compatível externo, como PyPI, TestPyPI, Nexus, Artifactory ou outro registry privado.

## Artefatos incluídos

```text
deploy/package-registry/
├── README_AGENT_FRAMEWORK_PACKAGE_REGISTRY.md
├── scripts/
│   ├── build_agent_framework.sh
│   ├── publish_azure_artifacts_local.sh
│   ├── install_from_azure_artifacts.sh
│   └── create_github_release_package.sh

azure-pipelines-agent-framework-publish.yml
.github/workflows/
├── agent-framework-build-release.yml
└── agent-framework-publish-pypi.yml

templates/agent_template_backend/examples/
├── requirements.azure-artifacts.example.txt
├── requirements.github-release.example.txt
└── Dockerfile.registry-consumer.example
```

---

# 1. Build local do pacote

Execute a partir da raiz do projeto:

```bash
./deploy/package-registry/scripts/build_agent_framework.sh
```

Saída esperada:

```text
libs/agent_framework/dist/
├── agent_framework-0.1.0-py3-none-any.whl
└── agent_framework-0.1.0.tar.gz
```

A versão vem de:

```text
libs/agent_framework/pyproject.toml
```

Exemplo:

```toml
[project]
name = "agent-framework"
version = "0.1.0"
```

O import Python continua sendo:

```python
import agent_framework
```

Mesmo que o nome do pacote publicado seja `agent-framework`.

---

# 2. Publicação no Azure DevOps Artifacts

## 2.1 Criar feed

No Azure DevOps:

```text
Artifacts > Create Feed
```

Sugestão:

```text
agent-framework-feed
```

Permissões necessárias para a pipeline:

```text
Feed Publisher / Contributor
```

## 2.2 Pipeline Azure DevOps

Arquivo incluído na raiz:

```text
azure-pipelines-agent-framework-publish.yml
```

O trecho principal usa `TwineAuthenticate@1` e depois publica com `twine`:

```yaml
- task: TwineAuthenticate@1
  inputs:
    artifactFeed: '$(azureFeed)'

- script: |
    cd $(frameworkDir)
    python -m twine upload -r agent-framework-feed --config-file "$(PYPIRC_PATH)" dist/*
```

Ajuste a variável se seu feed tiver outro nome:

```yaml
variables:
  azureFeed: '$(System.TeamProject)/agent-framework-feed'
```

Para feed em escopo de organização, use apenas:

```yaml
azureFeed: 'agent-framework-feed'
```

## 2.3 Publicação local no Azure Artifacts

Exemplo:

```bash
export AZURE_ORG="minha-org"
export AZURE_PROJECT="AgentPlatform"
export AZURE_FEED="agent-framework-feed"
export AZURE_PAT="***"

./deploy/package-registry/scripts/build_agent_framework.sh
./deploy/package-registry/scripts/publish_azure_artifacts_local.sh
```

O PAT precisa de permissão:

```text
Packaging: Read & Write
```

## 2.4 Consumo pelo agente

Exemplo de instalação local:

```bash
export AZURE_ORG="minha-org"
export AZURE_PROJECT="AgentPlatform"
export AZURE_FEED="agent-framework-feed"
export AZURE_PAT="***"
export AGENT_FRAMEWORK_VERSION="0.1.0"

./deploy/package-registry/scripts/install_from_azure_artifacts.sh
```

No `requirements.txt` do agente, a dependência deve ficar assim:

```text
agent-framework==0.1.0
```

A URL e credenciais do feed devem ser passadas no build do Docker, não gravadas no arquivo.

---

# 3. Consumo em Dockerfile do agente

Exemplo incluído:

```text
templates/agent_template_backend/examples/Dockerfile.registry-consumer.example
```

Uso com Azure Artifacts:

```bash
docker build \
  -f templates/agent_template_backend/examples/Dockerfile.registry-consumer.example \
  --build-arg PIP_INDEX_URL="https://azdo:${AZURE_PAT}@pkgs.dev.azure.com/${AZURE_ORG}/${AZURE_PROJECT}/_packaging/${AZURE_FEED}/pypi/simple/" \
  --build-arg PIP_EXTRA_INDEX_URL="https://pypi.org/simple" \
  --build-arg AGENT_FRAMEWORK_VERSION="0.1.0" \
  -t agent-template-backend:0.1.0 \
  .
```

Recomendação de segurança para pipeline:

- nunca commitar PAT;
- usar secret variable;
- usar Docker BuildKit secret quando possível;
- limitar o PAT a Packaging Read para build de consumidores.

---

# 4. GitHub

## 4.1 GitHub Releases como distribuição de wheel

Arquivo incluído:

```text
.github/workflows/agent-framework-build-release.yml
```

Esse workflow é acionado por tags:

```bash
git tag agent-framework-v0.1.0
git push origin agent-framework-v0.1.0
```

Ele gera:

```text
libs/agent_framework/dist/*.whl
libs/agent_framework/dist/*.tar.gz
```

E publica como assets de uma GitHub Release.

Publicação local com GitHub CLI:

```bash
export GITHUB_REPOSITORY="org/agent_platform_oci"
export GITHUB_TOKEN="***"
export PACKAGE_VERSION="0.1.0"

./deploy/package-registry/scripts/build_agent_framework.sh
./deploy/package-registry/scripts/create_github_release_package.sh
```

## 4.2 Instalação a partir de GitHub Release

Exemplo:

```text
agent-framework @ https://github.com/<org>/<repo>/releases/download/agent-framework-v0.1.0/agent_framework-0.1.0-py3-none-any.whl
```

Para repositório privado, o build precisa de token com permissão de leitura no repositório.

## 4.3 GitHub Actions para PyPI-compatible registry

Arquivo incluído:

```text
.github/workflows/agent-framework-publish-pypi.yml
```

Use este workflow para publicar em um registry compatível com PyPI:

- PyPI;
- TestPyPI;
- Nexus;
- Artifactory;
- outro registry privado compatível.

Secrets esperados:

```text
PYPI_REPOSITORY_URL
PYPI_USERNAME
PYPI_PASSWORD
```

---

# 5. Ajuste no `agent_template_backend`

O `agent_template_backend` deve parar de instalar o framework por path local em produção.

Uso recomendado:

```text
agent-framework==0.1.0
```

Exemplo completo:

```text
templates/agent_template_backend/examples/requirements.azure-artifacts.example.txt
```

Em desenvolvimento local, você ainda pode usar modo editável:

```bash
pip install -e libs/agent_framework
```

Mas em OKE/produção, use sempre pacote versionado.

---

# 6. Fluxo recomendado de release

```bash
# 1. Atualizar versão
vi libs/agent_framework/pyproject.toml

# 2. Build local e validação
./deploy/package-registry/scripts/build_agent_framework.sh

# 3. Commit
git add libs/agent_framework/pyproject.toml deploy/package-registry .github/workflows azure-pipelines-agent-framework-publish.yml
git commit -m "Publish agent-framework package registry artifacts"

# 4. Tag
git tag agent-framework-v0.1.0
git push origin main --tags
```

A partir daí:

- Azure DevOps publica no Azure Artifacts;
- GitHub Actions publica wheel/sdist em GitHub Release;
- agentes consomem `agent-framework==0.1.0`.

---

# 7. Relação com OKE

No OKE, os Deployments continuam sendo apenas das aplicações:

```text
agent_template_backend
agent_gateway
channel_gateway
mcp_gateway
frontend
```

O `agent_framework` entra dentro da imagem Docker dessas aplicações durante o build via:

```bash
pip install agent-framework==0.1.0
```

Portanto, não existe:

```text
Deployment agent-framework
Service agent-framework
Pod agent-framework
LoadBalancer agent-framework
```

Existe apenas uma dependência versionada instalada dentro dos containers.

---

# 8. Estratégia de versionamento

Sugestão SemVer:

```text
MAJOR.MINOR.PATCH
```

Exemplos:

```text
0.1.0   primeira versão empacotada
0.2.0   nova funcionalidade compatível
0.2.1   correção sem quebra
1.0.0   baseline corporativa estável
```

Para agentes críticos, fixe a versão:

```text
agent-framework==1.0.0
```

Evite em produção:

```text
agent-framework>=1.0.0
```

---

# 9. Conclusão

A arquitetura correta é tratar o `agent_framework` como biblioteca corporativa versionada, publicada em um registry privado e consumida pelos agentes durante o build.

Para o seu cenário, a recomendação principal é:

```text
Azure DevOps Artifacts = registry Python privado principal
GitHub Releases       = distribuição alternativa quando o código estiver no GitHub
OKE                   = executa somente aplicações consumidoras do framework
```
