# D-013: Start as a modular monolith

Status: Accepted

API and worker run separately while sharing bounded Python packages and one transactional
database. Network services are introduced only with measured evidence.
