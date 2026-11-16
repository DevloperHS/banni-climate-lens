# Azure deploy cheat sheet (Student account)

## Names to remember
- Resource group: banni-rg
- Container app: banni-app
- Environment: banni-env
- Registry (ACR): bannilens32078
- Region: centralindia
- Image: bannilens32078.azurecr.io/banni-climate-lens:<tag>
- URL: https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io

## 4 things that matter on a Student account
1. `az acr build` does not work here (TasksOperationsNotAllowed). Build the image locally with docker and push it.
2. Use a NEW tag on every deploy (v5, v6...). Never reuse an old tag.
3. Add `--provenance=false --sbom=false` to the build, otherwise Container Apps may say the image is "not found".
4. Paste ONLY ONE BLOCK AT A TIME in the terminal. At the `az login` "Select a subscription" prompt, just press Enter — otherwise pasted commands get swallowed as an "Invalid selection".

## First time in a new Codespace
Install Azure CLI:

    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

Login (if prompted, just press Enter):

    az login --use-device-code

Check:

    az account show --query "{name:name, id:id}" -o table
    az acr list -g banni-rg --query "[0].name" -o tsv

## Daily work: code changed, now deploy

1. First commit + push (add specific folders, not `git add -A`):

        cd /workspaces/banni-climate-lens
        git status --short
        git add frontend backend deploy
        git commit -m "what changed"
        git push origin research-two-modes

2. Deploy (give a new tag):

        ./deploy/deploy.sh v5

   The script does: tag check, docker build, ACR login, push, containerapp update, health check.

## Manual way (without the script)

        ACR=bannilens32078
        docker build --provenance=false --sbom=false -t $ACR.azurecr.io/banni-climate-lens:v5 .

        az acr credential show -n $ACR --query "passwords[0].value" -o tsv | docker login $ACR.azurecr.io -u $ACR --password-stdin
        docker push $ACR.azurecr.io/banni-climate-lens:v5

Only after the push fully completes:

        az containerapp update -g banni-rg -n banni-app --image $ACR.azurecr.io/banni-climate-lens:v5

## Check after deploy

    URL=https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io
    curl -s $URL/api/health; echo
    curl -s -D - -o /dev/null $URL/report/index.html | grep -iE "^HTTP|x-frame|content-security"
    curl -s -o /dev/null -w "reports: %{http_code}\n" $URL/reports
    az containerapp logs show -g banni-rg -n banni-app --tail 100 | grep -iE "Traceback|500"

Then do Ctrl+Shift+R in the browser. Azure keeps old CSS/JS in cache.

Expected:
- health: "status":"ok", "auth_required_for_writes":true
- x-frame-options: SAMEORIGIN, frame-ancestors 'self'
- /reports: 200, no Traceback in logs

## Rollback (new version turned out bad)

    az acr repository show-tags -n bannilens32078 --repository banni-climate-lens -o tsv
    az containerapp update -g banni-rg -n banni-app --image bannilens32078.azurecr.io/banni-climate-lens:v2

(Replace v2 with any older tag that works.)

## Mistakes that have already happened
- `az acr build` -> TasksOperationsNotAllowed. Build + push locally instead.
- A failed `update` writes a bad tag into the app's template. The running revision keeps serving, but the next change gets stuck on that tag. First run `update` to put a known-good tag back.
- Commands slipping in between pastes -> `500`, `banni-test`, `leep 15` and other stray files got created. Add specific folders instead of `git add -A`.
- An empty variable ($ACR) -> "expected one argument" error. First run `echo $ACR`; if it's empty:

        ACR=$(az acr list -g banni-rg --query "[0].name" -o tsv)

## Token (secret `gcl-token`)
Length check (without printing the token, should be about 49):

    az containerapp secret show -g banni-rg -n banni-app --secret-name gcl-token --query value -o tsv | wc -c

Create a new token:

    az containerapp secret set -g banni-rg -n banni-app --secrets gcl-token=$(openssl rand -hex 24)
    az containerapp update -g banni-rg -n banni-app --revision-suffix r$RANDOM

Never send a token or password in chat, a GitHub issue, or a screenshot.

## Saving credit
- `--min-replicas 1` means the app always runs and keeps spending credit.
- Nothing to do for a few days: `az containerapp update -g banni-rg -n banni-app --min-replicas 0`
- After the demo/submission, remove everything: `az group delete -n banni-rg --yes`

## Auto-deploy (GitHub Actions)
`.github/workflows/deploy.yml` does not exist yet. When creating it, use docker build + push, not `az acr build`. The `workflow_dispatch` button only shows once the file is on the main branch.