# My Dev Commands Reference

## Navigation
```bash
cd ~/luci-crews          # Go to the luci-crews project folder
cd ~/LUCI                # Go to the main LUCI app folder (once cloned)
cd ~                     # Go back to home folder
```

## Opening Files
```bash
open -e ~/luci-crews/.env           # Open luci-crews environment variables
open -e ~/LUCI/.env.local           # Open LUCI app environment variables (once set up)
```

## Git (saving and sharing your work)
```bash
git status                          # See what files you've changed
git checkout -b feature/my-feature # Create a new branch for your work
git add .                           # Stage all your changes
git commit -m "describe what you did"  # Save your changes
git push origin feature/my-feature # Push your branch to GitHub
gh pr create                        # Create a pull request for Ron to review
```

## Running the Projects
```bash
# luci-crews (Python AI backend)
cd ~/luci-crews
uv run uvicorn src.luci_crews.main:app --reload --port 8001

# LUCI main app (once set up)
cd ~/LUCI
npm run dev
```

## Supabase (local database)
```bash
supabase start           # Start local database
supabase stop            # Stop local database
supabase status          # Get local database URLs and keys
```

## Checking Things
```bash
git branch               # See what branch you're on
docker --version         # Check Docker is running
gh auth status           # Check GitHub is logged in
```

## If Something Goes Wrong
```bash
git stash                # Temporarily save changes without committing
git checkout main        # Go back to the main branch
```
