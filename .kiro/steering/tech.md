# Tech Stack

## Core
- **Runtime**: Node.js v18+
- **Package Manager**: npm
- **Language**: TypeScript / JavaScript (frontend), Python (optional, for AI agents)
- **Cloud Provider**: AWS (sandbox account via Workshop Studio)

## Frontend
- React
- AWS Amplify Gen2 is an easy way to deploy the frontend. If Amplify supports other services the team needs (Authentication, Data/GraphQL API, Storage, Functions), those can be used too.

## Backend
- Teams are free to choose their own backend approach (Amplify backend, AWS CDK, AWS SDK, Console, etc.)
- Common AWS services: DynamoDB, Lambda, Cognito, S3, API Gateway
- Data Source: Mars Crop Knowledge Base via MCP server

## AI Agents (Optional)
- **Strands Agents SDK** (Python) — open-source SDK for building agents with tool use, LLM calls, and multi-step reasoning. Integrates with AWS Bedrock models. Install: `pip install strands-agents strands-agents-tools`
- **Amazon Bedrock AgentCore** — infrastructure for hosting, scaling, and operating AI agents. Recommended for deploying agentic applications.
- Any other agent framework is also fine — these are recommendations, not requirements.

## Kiro Powers
- Enable **Strands SDK** power for agent development guidance
- Enable **Amplify** power for frontend/Amplify patterns
- Enable **AgentCore** power for deployment guidance

## Common Commands

```bash
# Install dependencies
npm install

# Start frontend dev server
npm run dev

# Start Amplify backend sandbox (if using Amplify for backend)
npx ampx sandbox

# Verify AWS credentials
aws sts get-caller-identity

# Create a new Amplify project
npm create amplify@latest <project-name>

# Install Strands SDK (if building AI agents)
pip install strands-agents strands-agents-tools
```

## Notes
- AWS credentials are temporary (Workshop Studio). Re-copy them if you get auth errors.
- The MCP config lives at `.kiro/settings/mcp.json` for the Mars Crop Knowledge Base.
- MCP endpoint: `https://kb-start-hack-gateway-buyjtibfpg.gateway.bedrock-agentcore.us-east-2.amazonaws.com/mcp`
