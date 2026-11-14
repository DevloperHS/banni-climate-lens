# Azure deploy cheat sheet (Student account)

## Naam yaad rakho
- Resource group: banni-rg
- Container app: banni-app
- Environment: banni-env
- Registry (ACR): bannilens32078
- Region: centralindia
- Image: bannilens32078.azurecr.io/banni-climate-lens:<tag>
- URL: https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io

## Student account ki 4 zaroori baatein
1. `az acr build` yahan kaam nahi karta (TasksOperationsNotAllowed). Image local docker se build karke push karo.
2. Har deploy par NAYA tag use karo (v5, v6...). Purana tag dobara mat do.
3. Build mein `--provenance=false --sbom=false` lagao, warna Container Apps image "not found" bol sakta hai.
4. Terminal mein EK BAAR MEIN EK HI BLOCK paste karo. `az login` ke "Select a subscription" prompt par sirf Enter dabao, warna paste kiye commands "Invalid selection" bankar kho jaate hain.

## Naye Codespace mein pehli baar
Azure CLI install:

    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

Login (prompt aaye toh sirf Enter):

    az login --use-device-code

Check:

    az account show --query "{name:name, id:id}" -o table
    az acr list -g banni-rg --query "[0].name" -o tsv

## Roz ka kaam: code badla, ab deploy karna hai

1. Pehle code commit + push (specific folders add karo, `git add -A` nahi):

        cd /workspaces/banni-climate-lens
        git status --short
        git add frontend backend deploy
        git commit -m "kya badla"
        git push origin research-two-modes

2. Deploy (naya tag do):

        ./deploy/deploy.sh v5

   Script yeh karta hai: tag check, docker build, ACR login, push, containerapp update, health check.

## Manual tareeka (script ke bina)

        ACR=bannilens32078
        docker build --provenance=false --sbom=false -t $ACR.azurecr.io/banni-climate-lens:v5 .

        az acr credential show -n $ACR --query "passwords[0].value" -o tsv | docker login $ACR.azurecr.io -u $ACR --password-stdin
        docker push $ACR.azurecr.io/banni-climate-lens:v5

Push poora hone ke baad hi:

        az containerapp update -g banni-rg -n banni-app --image $ACR.azurecr.io/banni-climate-lens:v5

## Deploy ke baad check

    URL=https://banni-app.livelygrass-8df5f932.centralindia.azurecontainerapps.io
    curl -s $URL/api/health; echo
    curl -s -D - -o /dev/null $URL/report/index.html | grep -iE "^HTTP|x-frame|content-security"
    curl -s -o /dev/null -w "reports: %{http_code}\n" $URL/reports
    az containerapp logs show -g banni-rg -n banni-app --tail 100 | grep -iE "Traceback|500"

Phir browser mein Ctrl+Shift+R karo. Azure par purana CSS/JS cache mein reh jata hai.

Expected:
- health: "status":"ok", "auth_required_for_writes":true
- x-frame-options: SAMEORIGIN, frame-ancestors 'self'
- /reports: 200, logs mein Traceback nahi

## Rollback (naya version kharab nikla)

    az acr repository show-tags -n bannilens32078 --repository banni-climate-lens -o tsv
    az containerapp update -g banni-rg -n banni-app --image bannilens32078.azurecr.io/banni-climate-lens:v2

(v2 ki jagah koi purana kaam karta hua tag likho.)

## Galtiyan jo pehle ho chuki hain
- `az acr build` -> TasksOperationsNotAllowed. Local build+push karo.
- Failed `update` app ke template mein kharab tag likh deta hai. Chalta revision serve hota rehta hai, par agla badlav usi tag par atakta hai. Pehle `update` se known-good tag wapas lagao.
- Paste ke beech commands prompt mein ghus gaye -> `500`, `banni-test`, `leep 15` jaisi stray files ban gayi. `git add -A` ki jagah specific folders add karo.
- Variable khaali hona ($ACR) -> "expected one argument" error. Pehle `echo $ACR` karo, khaali ho toh:

        ACR=$(az acr list -g banni-rg --query "[0].name" -o tsv)

## Token (secret `gcl-token`)
Lambai check (token dikhe bina, ~49 aana chahiye):

    az containerapp secret show -g banni-rg -n banni-app --secret-name gcl-token --query value -o tsv | wc -c

Naya token banana:

    az containerapp secret set -g banni-rg -n banni-app --secrets gcl-token=$(openssl rand -hex 24)
    az containerapp update -g banni-rg -n banni-app --revision-suffix r$RANDOM

Token ya password kabhi chat, GitHub issue ya screenshot mein mat bhejo.

## Credit bachana
- `--min-replicas 1` ka matlab app hamesha chalta hai aur credit khata hai.
- Kuch din kaam nahi hai: `az containerapp update -g banni-rg -n banni-app --min-replicas 0`
- Demo/submission ke baad sab hatao: `az group delete -n banni-rg --yes`

## Auto-deploy (GitHub Actions)
`.github/workflows/deploy.yml` abhi nahi hai. Banate waqt `az acr build` nahi, docker build + push use karna. `workflow_dispatch` ka button tabhi dikhega jab file main branch par ho.
