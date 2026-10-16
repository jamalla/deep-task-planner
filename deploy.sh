#!/usr/bin/env bash
# Build and deploy Deep Task Planner to AWS Lambda (+ public Function URL).
# Run from AWS CloudShell in the repo folder:
#
#   bash deploy.sh             # first deploy: asks for your OpenAI key (hidden)
#   bash deploy.sh             # later: updates code, keeps key + access code
#   bash deploy.sh --set-key   # replace the OpenAI key
#
set -euo pipefail
cd "$(dirname "$0")"

FUNCTION_NAME="${FUNCTION_NAME:-deep-task-planner}"
ROLE_NAME="${ROLE_NAME:-deep-task-planner-lambda-role}"
REGION="${REGION:-us-east-1}"
MODEL="${OPENAI_MODEL:-gpt-5-mini}"
export AWS_DEFAULT_REGION="$REGION"
SET_KEY=false; [ "${1:-}" = "--set-key" ] && SET_KEY=true

echo "==> Region $REGION | function $FUNCTION_NAME"

# ---------- 1. Package: Linux x86_64 wheels for Python 3.13 + our app/ ----------
echo "==> Building package (Linux wheels for Python 3.13)"
rm -rf build function.zip
python3 -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install --quiet --target build \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 \
  --only-binary=:all: -r requirements.txt
cp -r app build/
find build -name "__pycache__" -type d -prune -exec rm -rf {} +
(cd build && zip -q -r ../function.zip .)
echo "    function.zip = $(du -h function.zip | cut -f1) (direct upload limit: 50 MB)"

# ---------- 2. IAM role: the function may only write its own logs ----------
if ! ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text 2>/dev/null); then
  echo "==> Creating IAM role $ROLE_NAME (CloudWatch Logs only)"
  ROLE_ARN=$(aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --query Role.Arn --output text)
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "    waiting for IAM to propagate..."; sleep 12
fi

# ---------- 3. Environment: keep existing values, fill what's missing ----------
EXISTING='{}'
if aws lambda get-function --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  EXISTS=true
  EXISTING=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" \
    --query 'Environment.Variables' --output json)
  [ "$EXISTING" = "null" ] && EXISTING='{}'
else
  EXISTS=false
fi
HAS_KEY=$(python3 -c 'import json,sys; print("yes" if json.loads(sys.argv[1]).get("OPENAI_API_KEY") else "no")' "$EXISTING")
OPENAI_KEY=""
if [ "$HAS_KEY" = "no" ] || $SET_KEY; then
  read -r -s -p "Paste your OpenAI API key (hidden): " OPENAI_KEY; echo
  [ -z "$OPENAI_KEY" ] && { echo "No key entered, aborting."; exit 1; }
fi
ENV_JSON=$(OPENAI_KEY="$OPENAI_KEY" python3 - "$EXISTING" "$MODEL" <<'PY'
import json, os, secrets, sys
env = json.loads(sys.argv[1]) or {}
env.setdefault("ACCESS_CODE", secrets.token_urlsafe(18))
env["OPENAI_MODEL"] = sys.argv[2]
if os.environ.get("OPENAI_KEY"):
    env["OPENAI_API_KEY"] = os.environ["OPENAI_KEY"]
print(json.dumps({"Variables": env}))
PY
)
printf '%s' "$ENV_JSON" > /tmp/dtp-env.json; chmod 600 /tmp/dtp-env.json   # avoid key in process list

# ---------- 4. Create or update the function ----------
if $EXISTS; then
  echo "==> Updating code"
  aws lambda update-function-code --function-name "$FUNCTION_NAME" --zip-file fileb://function.zip >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FUNCTION_NAME"
  echo "==> Updating configuration"
  aws lambda update-function-configuration --function-name "$FUNCTION_NAME" \
    --timeout 300 --memory-size 1024 --environment file:///tmp/dtp-env.json >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FUNCTION_NAME"
else
  echo "==> Creating function"
  aws lambda create-function --function-name "$FUNCTION_NAME" \
    --runtime python3.13 --architectures x86_64 \
    --handler app.handler.lambda_handler --role "$ROLE_ARN" \
    --zip-file fileb://function.zip --timeout 300 --memory-size 1024 \
    --environment file:///tmp/dtp-env.json >/dev/null
  aws lambda wait function-active-v2 --function-name "$FUNCTION_NAME"
fi
rm -f /tmp/dtp-env.json

# ---------- 5. Public HTTPS endpoint (the API itself needs the access code) ----------
if ! URL=$(aws lambda get-function-url-config --function-name "$FUNCTION_NAME" --query FunctionUrl --output text 2>/dev/null); then
  echo "==> Creating Function URL"
  URL=$(aws lambda create-function-url-config --function-name "$FUNCTION_NAME" \
    --auth-type NONE --query FunctionUrl --output text)
  aws lambda add-permission --function-name "$FUNCTION_NAME" --statement-id PublicUrl \
    --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$FUNCTION_NAME" --statement-id PublicUrlInvoke \
    --action lambda:InvokeFunction --principal "*" --invoked-via-function-url >/dev/null 2>&1 || true
fi

echo "==> Smoke test"
curl -s -o /dev/null -w "    GET /health -> HTTP %{http_code}\n" "${URL}health" || true

CODE=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" \
  --query Environment.Variables.ACCESS_CODE --output text)
echo
echo "==> Done!"
echo "    Chat page:   $URL"
echo "    Access code: $CODE   (paste it in the chat page, top right)"
