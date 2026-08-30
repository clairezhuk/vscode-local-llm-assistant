# Project Nexus
## Security Overview
This project uses a stateless authentication system. All requests must include a header:
`Authorization: Bearer <token>`. 
The tokens are generated using JSON Web Tokens (JWT) with HS256 algorithm.
Do not use Session Cookies as they are deprecated in this version.