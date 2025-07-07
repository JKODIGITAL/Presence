#!/bin/bash
# Professional Frontend Development Startup Script
# Presence Project - Frontend Development Server

set -euo pipefail

# Configuration
readonly SCRIPT_NAME="$(basename "$0")"
readonly APP_DIR="/app"
readonly NODE_MODULES_DIR="${APP_DIR}/node_modules"
readonly PACKAGE_JSON="${APP_DIR}/package.json"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

# Environment validation
validate_environment() {
    log_info "Validating development environment..."
    
    # Check if package.json exists
    if [[ ! -f "$PACKAGE_JSON" ]]; then
        log_error "package.json not found at $PACKAGE_JSON"
        log_error "Ensure the frontend directory is properly mounted"
        exit 1
    fi
    
    # Check Node.js version
    local node_version
    node_version="$(node --version)"
    log_info "Node.js version: $node_version"
    
    # Check npm version  
    local npm_version
    npm_version="$(npm --version)"
    log_info "npm version: $npm_version"
    
    log_success "Environment validation complete"
}

# Dependency management
install_dependencies() {
    log_info "Managing project dependencies..."
    
    cd "$APP_DIR"
    
    # Check if node_modules exists and has content
    if [[ -d "$NODE_MODULES_DIR" ]] && [[ -n "$(ls -A "$NODE_MODULES_DIR" 2>/dev/null)" ]]; then
        log_info "node_modules directory exists, checking dependency integrity..."
        
        # Check Vite version specifically (must be 5.x for Node 18 compatibility)
        local vite_version
        if vite_version=$(npm list vite --depth=0 2>/dev/null | grep vite@ | sed 's/.*vite@//'); then
            log_info "Found Vite version: $vite_version"
            
            # Check if Vite version is compatible (5.x)
            if [[ "$vite_version" =~ ^5\. ]]; then
                log_success "Vite version is Node.js 18 compatible"
                return 0
            else
                log_warn "Vite version ($vite_version) incompatible with Node.js 18, reinstalling..."
            fi
        else
            log_warn "Vite not found, reinstalling dependencies..."
        fi
    fi
    
    # Clean installation
    log_info "Performing clean dependency installation..."
    rm -rf node_modules package-lock.json .vite
    
    # Install dependencies with proper flags for Docker environment
    npm install --include=dev --no-bin-links --no-audit --no-fund
    
    # Verify critical dependencies
    if [[ ! -d "$NODE_MODULES_DIR/vite" ]]; then
        log_error "Vite not found after installation"
        log_info "Attempting to install Vite explicitly..."
        npm install vite@latest --save-dev --no-bin-links
    fi
    
    log_success "Dependencies installed successfully"
}

# Start development server
start_dev_server() {
    log_info "Starting Vite development server..."
    
    cd "$APP_DIR"
    
    # Set environment variables
    export NODE_ENV=development
    # Use environment variable if set, otherwise use Docker service name
    export VITE_API_URL="${VITE_API_URL:-http://presence-api:9000}"
    
    # Try different methods to start Vite (PRIORITIZE LOCAL COMPATIBLE VERSION)
    local vite_executable=""
    
    # Method 1: ALWAYS try local Vite first (guaranteed compatible version)
    if [[ -x "node_modules/.bin/vite" ]]; then
        vite_executable="./node_modules/.bin/vite"
        log_info "Using local Vite binary (Node.js 18 compatible)"
    # Method 2: Direct node execution of local Vite
    elif [[ -f "node_modules/vite/bin/vite.js" ]]; then
        vite_executable="node node_modules/vite/bin/vite.js"
        log_info "Using direct node execution of local Vite"
    # Method 3: Use npx (will use local version)
    elif command -v npx >/dev/null 2>&1; then
        vite_executable="npx vite"
        log_info "Using npx to run local Vite"
    # Method 4: Last resort - force install local vite and use it
    else
        log_warn "No local Vite found, installing locally..."
        npm install vite@5.4.10 --save-dev --no-bin-links
        if [[ -x "node_modules/.bin/vite" ]]; then
            vite_executable="./node_modules/.bin/vite"
            log_info "Using newly installed local Vite"
        else
            log_error "Failed to install compatible Vite version"
            exit 1
        fi
    fi
    
    log_success "Starting development server on 0.0.0.0:3000"
    log_info "Server will be accessible at http://localhost:3000"
    
    # Execute Vite with proper configuration
    exec $vite_executable --host 0.0.0.0 --port 3000 --force
}

# Main execution
main() {
    log_info "=== Presence Frontend Development Server ==="
    log_info "Starting $SCRIPT_NAME..."
    
    validate_environment
    install_dependencies
    start_dev_server
}

# Error handling
trap 'log_error "Script failed on line $LINENO"' ERR

# Execute main function
main "$@"