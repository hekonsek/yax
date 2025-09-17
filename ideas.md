# Yax usage ideas

Distinguish building agentsmd (urls only) from discovery of building urls. `yax (agentsmd index) discover` should be a dedicated process. `yax (agentsmd) build` should be updating only added url to the latest version. 

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
    discover:
      labels:
      - terraform
      - gcp
     exclude:
      labels:
      - aws 


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