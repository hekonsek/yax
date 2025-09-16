# Yax usage ideas

Files:
- yax-build-agentsmd.yml (aka yax.yml)
- yax-build-index.yml
- yax-index.yml

yax.yml

build:
  index:
    from:
  ...

build:
  agentsmd:
    from:
    ...

build:
  from:
    index:
      labels:
      - terraform
      - gcp
    exclude:
      labels:
      - aws 

build:
  from:
    urls:
      - https://raw.github.com/hekonsek/agents-terraform/_agents.md

build:
  ...
  target: "_agents.md"

build:
  from:
    files: "adrs/*.md"


index:
  sources:
  - ...



Initial index:
- adr-terraform
- terraform-gcp-vpc
- terraform-gcp-gke