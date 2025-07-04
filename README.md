# Kuadrant E2E testsuite

This repository contains end-to-end tests for Kuadrant project. It supports running tests either against standalone Authorino and Authorino Operator, or the entire Kuadrant, both Service Protection and MGC. For more information about Kuadrant, please visit https://kuadrant.io/

## Requirements

### Authorino standalone tests
* Kubernetes cluster
* Authorino Operator installed
* Use `authorino-standalone` make target

### Service Protection tests
* Kubernetes cluster
* Kuadrant Operator installed
* Use `test` make target

### DNSPolicy tests
* Existing DNS provider Secret named `aws-credentials` (name defined in `control_plane.provider_secret`) with annotation containing the base domain. Example AWS provider Secret:
```yaml
kind: Secret
apiVersion: v1
metadata:
  name: aws-credentials
  namespace: kuadrant
  annotations:
    base_domain: example.com
data:
  AWS_ACCESS_KEY_ID: <key>
  AWS_REGION: <region>
  AWS_SECRET_ACCESS_KEY: <key>
type: kuadrant.io/aws
```

### TLSPolicy tests
* Kuadrant QE self-signed CA ClusterIssuer which can be found here [kuadrant-helm-install](https://github.com/azgabur/kuadrant-helm-install/tree/main/instances/templates/cert-manager)
* (Optional) Existing lets-encrypt ClusterIssuer or Issuer, named `letsencrypt-staging-issuer` (name defined in `letsencrypt.issuer.name`)

## Configuration

Kuadrant testsuite uses [Dynaconf](https://www.dynaconf.com/) for configuration, which means you can specify the configuration through either settings files in `config` directory or through environmental variables. 
All the required and possible configuration options can be found in `config/settings.local.yaml.tpl`

### Kubernetes auto-fetching

Some configuration options can be fetched from Kubernetes if there are correctly deployed [tools](https://github.com/3scale-qe/tools).
Tools can be deployed by using `overlays/kuadrant` overlay like this:
```bash
oc apply -k overlays/kuadrant/ --namespace tools
```

### Settings files

Settings files are located at `config` directory and are in `yaml` format. To use them for local development, you can create `settings.local.yaml` and put all settings there.

### Environmental variables

You can also configure all the settings through environmental variables as well. We use prefix `KUADRANT` so the variables can look like this:
```bash
export KUADRANT_RHSSO__url="https://my-sso.net"
```
You can find more info on the [Dynaconf wiki page](https://www.dynaconf.com/envvars/)

## Usage

You can run and manage environment for testsuite with the included Makefile, but the recommended way how to run the testsuite is from Container image

### Local development setup

Requirements:
* Python 3.11+
* [poetry](https://python-poetry.org/)
* [CFSSL](https://github.com/cloudflare/cfssl)
* [kubectl](https://kubernetes.io/docs/reference/kubectl/) (kubectl)

If you have all of those, you can run ```make poetry``` to install virtual environment and all dependencies
To run all tests you can then use ```make test```

### Running from container

For just running tests, the container image is the easiest option, you can log in to Kubernetes and then run it like this

If you omit any options, Testsuite will run only subset of tests that don't require that variable e.g. not providing Auth0 will result in skipping Auth0 tests.

NOTE: For binding kubeconfig file, the "others" need to have permission to read, otherwise it will not work.
The results and reports will be saved in `/test-run-results` in the container.

#### With tools setup

```bash
podman run \
	-v $HOME/.kube/config:/run/kubeconfig:z \
	-e KUADRANT_SERVICE_PROTECTION__PROJECT=authorino \
	-e KUADRANT_SERVICE_PROTECTION__PROJECT2=authorino2 \
	-e KUADRANT_AUTH0__url="AUTH0_URL" \
	-e KUADRANT_AUTH0__client_id="AUTH0_CLIENT_ID" \
	-e KUADRANT_AUTH0__client_secret="AUTH0_CLIENT_SECRET" \	
	quay.io/kuadrant/testsuite:latest
```

#### Without tools

```bash
podman run \
	-v $HOME/.kube/config:/run/kubeconfig:z \
	-e KUADRANT_SERVICE_PROTECTION__PROJECT=authorino \
	-e KUADRANT_SERVICE_PROTECTION__PROJECT2=authorino2 \
	-e KUADRANT_KEYCLOAK__url="https://my-sso.net" \
	-e KUADRANT_KEYCLOAK__password="ADMIN_PASSWORD" \
	-e KUADRANT_KEYCLOAK__username="ADMIN_USERNAME" \
	-e KUADRANT_AUTH0__url="AUTH0_URL" \
	-e KUADRANT_AUTH0__client_id="AUTH0_CLIENT_ID" \
	-e KUADRANT_AUTH0__client_secret="AUTH0_CLIENT_SECRET" \
	quay.io/kuadrant/testsuite:latest
```

## Developing tests

For developing tests for Authorino you might need to know content of the authorization JSON, you can do that through this AuthConfig, which will return all the context in the response

```yaml
apiVersion: authorino.kuadrant.io/v1beta3
kind: AuthConfig
metadata:
  name: example
spec:
  hosts:
    - '*'
  response:
    success:
      headers:
        auth-json:
          json:
            properties:
              auth:
                selector: auth
              context:
                selector: context
```

Another thing which might helpful is using playground for developing OPA policies https://play.openpolicyagent.org/.
