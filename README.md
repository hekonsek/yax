# yax: You Are eXpert

`yax` goal is to arm your AI agents with your expert knowledge.

Yax promotes generating and reusing `AGENTS.md` file containing instructions for coding agents (like Cursor, Claude Code, Codex, etc) on how to work on your projects.

## Usage

Let's say that IaC (Infrastructure As Code) subject matter experts at your organization (`Acme`) created two `AGENTS.md` files containing ADRs (Architecture Decision Records) describing best practicies that you should follow when using Terraform and working with AWS (Amazon Web Services).

If you're DevOps Engineer that is tasked to work on infra project that involves AWS, you can create the following Yax configuration file named `yax.yml` in your project to easily generate `AGENTS.md`. Such file automatically instructs your coding agent to follow your organization best practices for Terraform and AWS.

```yml
# yax.yml
build:
  agentsmd:
    from:
      - https://raw.githubusercontent.com/acme/adr-terraform/refs/heads/main/_agents.md
      - https://raw.githubusercontent.com/acme/adr-gcp/refs/heads/main/_agents.md      
```

Now you can just generate `AGENTS.md` file using `yax`:

```
$ yax build
Generated agents markdown at AGENTS.md.
```

That's it! You just instructed your local coding agent to follow your organization's subject matter experts guidance. 