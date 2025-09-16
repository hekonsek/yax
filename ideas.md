# Yax usage ideas

Files:
- yax-build-agentsmd.yml (aka yax.yml)
- yax-build-index.yml
- yax-index.yml

build:
  index:
    from:
  ...


build:
  agentsmd:
  from:
    index:
      labels:
      - terraform
      - gcp
    exclude:
      labels:
      - aws 


build:
  ...
  target: "_agents.md"

build:
  from:
    files: "adrs/*.md"


index:
  sources:
  - ...

Current index:
- adr-terraform

Target index:
- adr-terraform
- terraform-gcp-vpc
- terraform-gcp-gke


Add support for ADR tools?