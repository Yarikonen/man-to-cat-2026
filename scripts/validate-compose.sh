#!/bin/bash

# Docker Compose Configuration Validation Script
# Validates YAML syntax, checks for common anti-patterns, and validates port mappings
# Exits with status 0 if valid, 1 if issues found

# Color coding for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

set -e

COMPOSE_FILE="${1:-docker-compose.infrastructure.yml}"

# Validate that docker-compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}ERROR: Docker Compose file not found: $COMPOSE_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}Validating infrastructure configuration...${NC}"
echo "File: $COMPOSE_FILE"
echo

# Test 1: YAML syntax validation
echo -e "${YELLOW}[TEST 1] YAML syntax validation...${NC}"
if docker-compose -f "$COMPOSE_FILE" config > /dev/null 2>&1; then
    echo -e "${GREEN}✓ YAML syntax is valid${NC}"
else
    echo -e "${RED}✗ YAML syntax errors detected${NC}"
    docker-compose -f "$COMPOSE_FILE" config
    exit 1
fi
echo

# Test 2: Check hardcoded passwords (anti-pattern)
echo -e "${YELLOW}[TEST 2] Checking for hardcoded passwords...${NC}"
if grep -E "password:|PASSWORD=|PASS=" "$COMPOSE_FILE" | grep -E "(password|admin|root|secret)"; then
    echo -e "${YELLOW}⚠ WARNING: Potential hardcoded passwords found (use environment variables)${NC}"
    # Don't fail build, just warn
else
    echo -e "${GREEN}✓ No hardcoded passwords found${NC}"
fi
echo

# Test 3: Validate health checks are defined
echo -e "${YELLOW}[TEST 3] Checking health checks...${NC}"
HEALTH_CHECKS=$(grep -c "healthcheck:" "$COMPOSE_FILE" || echo "0")
echo "Found $HEALTH_CHECKS health check definitions"
if [ "$HEALTH_CHECKS" -lt 5 ]; then
    echo -e "${YELLOW}⚠ WARNING: Expected at least 5 health checks, found $HEALTH_CHECKS${NC}"
else
    echo -e "${GREEN}✓ Adequate health checks defined${NC}"
fi
echo

# Test 4: Check port conflicts
echo -e "${YELLOW}[TEST 4] Checking for port conflicts...${NC}"
PORTS=$(grep -E '^\s*- "[0-9]+:' "$COMPOSE_FILE" | wc -l | tr -d ' ')
echo "Found $PORTS port mappings"

# Extract host ports
HOST_PORTS=$(grep -E '^\s*- "[0-9]+' "$COMPOSE_FILE" | grep -oE '"[0-9]+' | grep -oE '[0-9]+' | sort -n)

# Check for duplicates
DUPLICATE_PORTS=$(echo "$HOST_PORTS" | uniq -d | wc -l | tr -d ' ')
if [ "$DUPLICATE_PORTS" -gt 0 ]; then
    echo -e "${RED}✗ Port conflicts detected: $(echo "$HOST_PORTS" | uniq -d)${NC}"
    exit 1
else
    echo -e "${GREEN}✓ No port conflicts found${NC}"
fi
echo

# Test 5: Validate depends_on configurations
echo -e "${YELLOW}[TEST 5] Checking depends_on configurations...${NC}"
depend_on_count=$(grep -c "depends_on:" "$COMPOSE_FILE" || echo "0")
echo "Found $depend_on_count depends_on sections"

# Check for service_healthy conditions (best practice)
health_conditions=$(grep -c "service_healthy" "$COMPOSE_FILE" || echo "0")
echo "Including $health_conditions service_healthy conditions (best practice)"
if [ "$health_conditions" -lt 2 ]; then
    echo -e "${YELLOW}⚠ WARNING: Consider adding service_healthy conditions for better startup order${NC}"
fi

if [ "$depend_on_count" -lt 2 ]; then
    echo -e "${YELLOW}⚠ WARNING: Expected at least 2 depends_on configurations, found $depend_on_count${NC}"
else
    echo -e "${GREEN}✓ Adequate depends_on configurations${NC}"
fi
echo

# Test 6: Validate volume mappings
echo -e "${YELLOW}[TEST 6] Validating volume mappings...${NC}"
VOLUMES=$(grep -c "volumes:" "$COMPOSE_FILE" || echo "0")
echo "Found $VOLUMES volume sections"

# Check for local paths
LOCAL_VOLUMES=$(grep -E "^\s*- \./" "$COMPOSE_FILE" | wc -l | tr -d ' ')
echo "Found $LOCAL_VOLUMES host volume mappings"
if [ "$LOCAL_VOLUMES" -gt 10 ]; then
    echo -e "${YELLOW}⚠ WARNING: Many host volume mappings, consider using named volumes${NC}"
else
    echo -e "${GREEN}✓ Reasonable number of volume mappings${NC}"
fi
echo

# Test 7: Validate restart policies
echo -e "${YELLOW}[TEST 7] Checking restart policies...${NC}"
RESTART_POLICIES=$(grep "restart:" "$COMPOSE_FILE" | grep -v "restart: \"no\"" | wc -l | tr -d ' ')
echo "Found $RESTART_POLICIES restart policies configured"
if [ "$RESTART_POLICIES" -lt 3 ]; then
    echo -e "${YELLOW}⚠ WARNING: Consider adding restart policies for production use${NC}"
else
    echo -e "${GREEN}✓ Restart policies configured${NC}"
fi
echo

# Test 8: Validate environment variable usage
echo -e "${YELLOW}[TEST 8] Checking environment variable usage...${NC}"
ENV_VARS=$(grep -c '\${' "$COMPOSE_FILE" || echo "0")
echo "Found $ENV_VARS environment variable substitutions"
if [ "$ENV_VARS" -lt 3 ]; then
    echo -e "${YELLOW}⚠ WARNING: Consider using environment variables for credentials${NC}"
else
    echo -e "${GREEN}✓ Environment variables used appropriately${NC}"
fi
echo

# Test 9: Check services network configuration
echo -e "${YELLOW}[TEST 9] Checking network configuration...${NC}"
NETWORK_SECTIONS=$(grep -c "networks:" "$COMPOSE_FILE" || echo "0")
NETWOR_DEFINITIONS=$(grep -A5 "networks:" "$COMPOSE_FILE" | grep -c "driver:" || echo "0")
echo "Found $NETWORK_SECTIONS network configurations with $NETWOR_DEFINITIONS driver definitions"
if [ "$NETWOR_DEFINITIONS" -ge 1 ]; then
    echo -e "${GREEN}✓ Network isolation configured${NC}"
else
    echo -e "${YELLOW}⚠ WARNING: Consider defining custom networks for isolation${NC}"
fi
echo

# Test 10: Validate Prometheus configuration integration
echo -e "${YELLOW}[TEST 10] Checking Prometheus integration...${NC}"
if [ -f "prometheus.yml" ]; then
    echo -e "${GREEN}✓ prometheus.yml exists${NC}"
    # Check if prometheus is defined in compose
    if grep -q "prometheus:" "$COMPOSE_FILE"; then
        echo -e "${GREEN}✓ Prometheus service configured in docker-compose${NC}"
    else
        echo -e "${YELLOW}⚠ WARNING: prometheus.yml exists but Prometheus service not in compose${NC}"
    fi
else
    echo -e "${YELLOW}⚠ WARNING: prometheus.yml not found${NC}"
fi
echo

# Final summary
echo -e "${GREEN}Validation complete!${NC}"
echo

# Alert on security best practices
echo -e "${YELLOW}Security best practices to consider:${NC}"
echo "1. Use Docker secrets or environment files for credentials"
echo "2. Pin image versions with SHA256 checksums for reproducibility"
echo "3. Limit container capabilities with cap_drop/cap_add"
echo "4. Use read-only root filesystems where applicable"
echo "5. Configure resource limits to prevent noisy neighbors"

exit 0
