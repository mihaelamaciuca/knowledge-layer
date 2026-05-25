#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Layer, Project Initializer
# ─────────────────────────────────────────────────────────────────────────────
# Run this once after cloning the template to parameterize it for your project.
# Idempotent: re-running after the first successful run reports "already
# initialised" and exits 0 without touching files.
#
# Usage:
#   chmod +x scripts/init.sh
#   ./scripts/init.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Detect sed in-place flag once, BSD (macOS) vs GNU (Linux).
if sed --version >/dev/null 2>&1; then
    SED_INPLACE=(-i)        # GNU sed
else
    SED_INPLACE=(-i "")     # BSD sed
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Knowledge Layer, Project Initializer"
echo "═══════════════════════════════════════════════════════"
echo ""

# Already-initialised guard: if no files contain the placeholder, run is a no-op.
if ! grep -rq '{{PROJECT_NAME}}' \
        --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules \
        --exclude=init.sh \
        . 2>/dev/null; then
    echo "Already initialised: no {{PROJECT_NAME}} placeholders remain."
    echo "Re-running init.sh would be a no-op; nothing to do."
    exit 0
fi

# ── Get project name ─────────────────────────────────────────────────────────
read -rp "Project name (lowercase, no spaces, e.g. 'myapp'): " PROJECT_NAME

if [[ -z "$PROJECT_NAME" ]]; then
    echo "Error: project name cannot be empty."
    exit 1
fi

# Validate: lowercase alphanumeric + hyphens only
if [[ ! "$PROJECT_NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
    echo "Error: project name must be lowercase, start with a letter, and contain only letters, numbers, and hyphens."
    exit 1
fi

echo ""
echo "Project name: $PROJECT_NAME"
echo ""

# ── Replace placeholders ────────────────────────────────────────────────────
echo "Replacing {{PROJECT_NAME}} across all files..."

# Find all text files and replace the placeholder.
# Excludes .git, .venv, node_modules, and binary files.
find . -type f \
    -not -path './.git/*' \
    -not -path './.venv/*' \
    -not -path './node_modules/*' \
    -not -name '*.pyc' \
    -not -name 'init.sh' \
    | while read -r file; do
        if file "$file" | grep -q text; then
            if grep -q '{{PROJECT_NAME}}' "$file" 2>/dev/null; then
                sed "${SED_INPLACE[@]}" "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$file"
                echo "  Updated: $file"
            fi
        fi
    done

echo ""
echo "Done. All {{PROJECT_NAME}} placeholders replaced with '$PROJECT_NAME'."

# ── Print next steps ────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Next Steps"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "See QUICKSTART.md for the full bootstrap sequence. In short:"
echo ""
echo "1. Create a Supabase project."
echo "2. Apply the schema migration:"
echo "       psql \"\$DATABASE_URL\" -f scripts/migrations/001_schema.sql"
echo "   (Idempotent. Enables pgvector, creates every table and index"
echo "    the indexer and MCP server need.)"
echo "3. Copy .env.example to .env and fill in credentials."
echo "4. Deploy the MCP server to Railway (or any host that runs Python):"
echo "       Set DATABASE_URL, OPENAI_API_KEY, MCP_TOKEN_1, BASE_URL."
echo "5. Update .claude/settings.json with your Railway URL + bearer token."
echo "6. Add GitHub Actions secrets: DATABASE_URL, OPENAI_API_KEY."
echo "7. Start writing docs in docs/ (see docs/TEMPLATES/ for scaffolds)."
echo "8. Initial population once you have some docs:"
echo "       python3 scripts/populate.py --docs-dir docs --full-reindex"
echo ""
