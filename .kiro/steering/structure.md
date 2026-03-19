# Project Structure

This repo is a starter/template. Once the project is scaffolded, a typical structure looks like:

```
mars-agriculture-app/
├── amplify/              # Backend definitions (if using Amplify for backend services)
│   ├── auth/             # Authentication setup
│   ├── data/             # Database / API schema
│   └── backend.ts        # Backend entry point
├── src/                  # Frontend application code (React)
├── .kiro/
│   ├── settings/
│   │   └── mcp.json      # MCP server config (Mars Crop Knowledge Base)
│   └── steering/         # Steering rules for AI assistant
├── package.json
└── README.md
```

## Conventions
- Frontend code goes in `src/`.
- Backend approach is up to the team — Amplify, CDK, SDK, Console, etc.
- AI agent code (if using Strands SDK or similar) can live in its own directory (e.g., `agents/`).
- The MCP Knowledge Base is read-only reference data — don't try to write to it.
