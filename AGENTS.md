# Terminal session script instructions

## Accessing logs from local filesystem 

- If you can access `~/.cache/script` directory, it means that you can access terminal script session logs even without calling MCP server. Take advanatage of this fact and read these logs when needed.
- Terminal session script logs are generated using standard Linux `script` command.
- Terminal session script logs are named with timestamp indicating when session started.
- You can also rely on Linux file timestamps to see when file ws updated.

## How to make use of terminal session script logs

- When you are asked about some problem related to cli, check for recently updated terminal session scripts and see if you can see activities related to this topic.
- Check for logs modified within past 15 minutes.

## Examples

When you are working on Python application and user is complaining that something is not working, look for the latest sessions logs to see if there is soemthing related to the complaint.

When you are working on Terraform and user is complaining that something is not working, check recent sessions logs to see if he/she tried to applied Terraform files you're currently working on. 