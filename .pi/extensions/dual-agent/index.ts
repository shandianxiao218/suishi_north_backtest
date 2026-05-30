/**
 * 双 Agent 协作 Extension
 *
 * 架构师 (architect, GLM-5.1) 通过两个 tool 调度码农 (coder, GLM-4.7)：
 *
 * - dispatch_coder: 派 issue 给码农，等待完成标记
 * - review_pr: 获取 PR diff / 提交 review / 合并 PR
 *
 * 详见 docs/adr/0003-dual-agent-development-workflow.md
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { StringEnum } from "@earendil-works/pi-ai";
import { Type } from "typebox";

// ── 配置 ──────────────────────────────────────────────

const PROJECT_TAG = "SUISHI-NORTH";
const DONE_PREFIX = `::AGENT-DONE::${PROJECT_TAG}::`;
const DEFAULT_CODER_MODEL = "glm-4.7";
const UPGRADED_CODER_MODEL = "glm-5-turbo";
const UPGRADE_THRESHOLD = 2;

// ── 状态（会话级，重启后重置）──────────────────────────

/** issue_number → 连续 review 不通过次数 */
const reviewFailures = new Map<number, number>();

// ── 工具函数 ──────────────────────────────────────────

/** 执行命令，返回 stdout / stderr / exit code */
function execCmd(
  command: string,
  args: string[],
  cwd: string,
  stdinData?: string,
): Promise<{ stdout: string; stderr: string; code: number }> {
  return new Promise((resolve) => {
    const proc = spawn(command, args, {
      cwd,
      shell: true,
      stdio: stdinData ? ["pipe", "pipe", "pipe"] : ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
    proc.stderr.on("data", (d: Buffer) => (stderr += d.toString()));
    if (stdinData) {
      proc.stdin.write(stdinData);
      proc.stdin.end();
    }
    proc.on("close", (code) => resolve({ stdout, stderr, code: code ?? 1 }));
    proc.on("error", (err) => resolve({ stdout, stderr: err.message, code: 1 }));
  });
}

/** 获取当前 GitHub 仓库 owner/repo */
async function getRepo(cwd: string): Promise<string> {
  const r = await execCmd(
    "gh",
    ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
    cwd,
  );
  if (r.code !== 0) throw new Error(`获取 GitHub 仓库失败: ${r.stderr}`);
  return r.stdout.trim();
}

/** 从 PR 分支名或 body 推断关联的 issue 编号 */
async function getIssueFromPr(
  cwd: string,
  prNumber: number,
): Promise<number | null> {
  const r = await execCmd(
    "gh",
    ["pr", "view", String(prNumber), "--json", "headRefName,body"],
    cwd,
  );
  if (r.code !== 0) return null;
  try {
    const data = JSON.parse(r.stdout);
    // 分支名模式: feat/issue-42
    const m1 = data.headRefName?.match(/issue[_-](\d+)/i);
    if (m1) return parseInt(m1[1]);
    // body 模式: Closes #42
    const m2 = data.body?.match(/(?:close|fix|resolve)\s*#(\d+)/i);
    if (m2) return parseInt(m2[1]);
  } catch {
    /* ignore */
  }
  return null;
}

/** 查找码农 agent 定义文件 */
function findCoderAgentDef(cwd: string): string | null {
  const candidates = [
    path.join(cwd, ".pi", "agents", "coder.md"),
    path.join(os.homedir(), ".pi", "agent", "agents", "coder.md"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/** 解析 agent .md 文件的 frontmatter 和 body */
function parseAgentDef(filePath: string): {
  model?: string;
  systemPrompt: string;
} {
  const raw = fs.readFileSync(filePath, "utf-8");
  if (!raw.startsWith("---")) return { systemPrompt: raw };
  const end = raw.indexOf("---", 3);
  if (end === -1) return { systemPrompt: raw };
  const fm = raw.slice(3, end).trim();
  const systemPrompt = raw.slice(end + 3).trim();
  const modelMatch = fm.match(/^model:\s*(.+)$/m);
  return { model: modelMatch?.[1]?.trim(), systemPrompt };
}

/** 从文本中解析完成标记 */
function parseDoneMarker(text: string): Record<string, string> | null {
  const idx = text.indexOf(DONE_PREFIX);
  if (idx === -1) return null;
  const line = text.slice(idx).split("\n")[0];
  const result: Record<string, string> = {};
  for (const segment of line.split("::")) {
    const eq = segment.indexOf("=");
    if (eq !== -1) result[segment.slice(0, eq)] = segment.slice(eq + 1);
  }
  return Object.keys(result).length > 0 ? result : null;
}

/** 根据 issue 的 review 失败次数决定码农模型 */
function resolveCoderModel(issueNumber: number): string {
  return (reviewFailures.get(issueNumber) ?? 0) >= UPGRADE_THRESHOLD
    ? UPGRADED_CODER_MODEL
    : DEFAULT_CODER_MODEL;
}

/** 确定 pi 启动命令（直接用当前 node 进程的 pi 脚本） */
function getPiInvocation(
  extraArgs: string[],
): { command: string; args: string[]; useShell: boolean } {
  const script = process.argv[1];
  if (
    script &&
    !script.startsWith("/$bunfs/root/") &&
    fs.existsSync(script)
  ) {
    return {
      command: process.execPath,
      args: [script, ...extraArgs],
      useShell: false,
    };
  }
  const execName = path.basename(process.execPath).toLowerCase();
  if (!/^(node|bun)(\.exe)?$/.test(execName)) {
    return { command: process.execPath, args: extraArgs, useShell: false };
  }
  // fallback: 用系统 pi 命令（Windows 需要 shell 解析 .cmd）
  return { command: "pi", args: extraArgs, useShell: true };
}

// ── 码农子进程 ────────────────────────────────────────

interface CoderResult {
  success: boolean;
  issue: number;
  pr?: number;
  model: string;
  error?: string;
  output: string;
}

function runCoderProcess(
  cwd: string,
  issueNumber: number,
  branchName: string,
  model: string,
  systemPrompt: string,
  signal: AbortSignal | undefined,
  onUpdate: ((msg: string) => void) | undefined,
): Promise<CoderResult> {
  const task = [
    `你是码农（coder），负责实现以下任务：`,
    ``,
    `1. 用 gh issue view ${issueNumber} 读取 issue`,
    `2. git checkout -b ${branchName}`,
    `3. 阅读项目 AGENTS.md、CONTEXT.md、docs/adr/ 相关 ADR`,
    `4. 先写测试，再写实现`,
    `5. 运行 python -m pytest 确保全绿`,
    `6. git add + commit（中文 commit message）`,
    `7. git push -u origin ${branchName}`,
    `8. gh pr create --fill（关联 #${issueNumber}）`,
    `9. 输出完成标记（必须单独占一行，放在回复最后）`,
    ``,
    `成功标记：`,
    `${DONE_PREFIX}issue=${issueNumber}::pr=<PR编号>::status=success::model=${model}`,
    `失败标记：`,
    `${DONE_PREFIX}issue=${issueNumber}::status=failed::error=<原因>::model=${model}`,
  ].join("\n");

  return new Promise((resolve) => {
    // 写 system prompt 到临时文件
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-coder-"));
    const tmpFile = path.join(tmpDir, "system-prompt.md");
    fs.writeFileSync(tmpFile, systemPrompt, { encoding: "utf-8", mode: 0o600 });

    const pi = getPiInvocation([
      "--mode",
      "json",
      "-p",
      "--no-session",
      "--model",
      model,
      "--append-system-prompt",
      tmpFile,
      task,
    ]);

    const proc = spawn(pi.command, pi.args, {
      cwd,
      shell: pi.useShell,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdoutBuf = "";
    let stderrBuf = "";
    let lastText = "";
    let marker: Record<string, string> | null = null;
    let turns = 0;

    const processLine = (line: string) => {
      if (!line.trim()) return;
      try {
        const ev = JSON.parse(line);
        if (ev.type === "message_end" && ev.message?.role === "assistant") {
          turns++;
          for (const part of ev.message.content || []) {
            if (part.type === "text") {
              lastText += part.text + "\n";
              const m = parseDoneMarker(part.text);
              if (m) marker = m;
            }
          }
          onUpdate?.(`码农工作进行中... (${turns} 轮)`);
        }
      } catch {
        /* not JSON, ignore */
      }
    };

    proc.stdout.on("data", (d: Buffer) => {
      stdoutBuf += d.toString();
      const lines = stdoutBuf.split("\n");
      stdoutBuf = lines.pop() || "";
      for (const l of lines) processLine(l);
    });

    proc.stderr.on("data", (d: Buffer) => (stderrBuf += d.toString()));

    const cleanup = () => {
      try {
        fs.unlinkSync(tmpFile);
      } catch {
        /* ignore */
      }
      try {
        fs.rmdirSync(tmpDir);
      } catch {
        /* ignore */
      }
    };

    proc.on("close", (code) => {
      // flush remaining buffer
      if (stdoutBuf.trim()) processLine(stdoutBuf);
      cleanup();
      if (marker) {
        resolve({
          success: marker.status === "success",
          issue: parseInt(marker.issue || String(issueNumber)),
          pr: marker.pr ? parseInt(marker.pr) : undefined,
          model: marker.model || model,
          error: marker.error,
          output: lastText.slice(-3000),
        });
      } else {
        resolve({
          success: false,
          issue: issueNumber,
          model,
          error:
            code !== 0 ? `进程退出码 ${code}` : "未检测到完成标记",
          output: (lastText || stderrBuf).slice(-3000),
        });
      }
    });

    proc.on("error", (err) => {
      cleanup();
      resolve({
        success: false,
        issue: issueNumber,
        model,
        error: err.message,
        output: stderrBuf,
      });
    });

    if (signal) {
      const kill = () => {
        proc.kill("SIGTERM");
        setTimeout(() => {
          if (!proc.killed) proc.kill("SIGKILL");
        }, 5000);
      };
      if (signal.aborted) kill();
      else signal.addEventListener("abort", kill, { once: true });
    }
  });
}

// ── Extension 主入口 ──────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ══════════════════════════════════════════════════════
  // dispatch_coder
  // ══════════════════════════════════════════════════════

  pi.registerTool({
    name: "dispatch_coder",
    label: "派任务给码农",
    description: [
      "给码农派一个 GitHub issue 任务。",
      "码农在独立进程中：读 issue → 建分支 → 写代码 → 跑测试 → 提 PR。",
      "同一 issue 连续 2 次 review 不通过时，自动升级模型到 GLM-5-Turbo。",
    ].join(" "),
    promptSnippet: "派任务给码农实现 GitHub issue",
    promptGuidelines: [
      "使用 dispatch_coder 给码农派 issue 任务，码农在独立进程完成实现并提 PR。",
      "派任务前先用 bash 的 gh issue list 查看 ready-for-agent 标签的 issue。",
    ],
    parameters: Type.Object({
      issue_number: Type.Number({ description: "GitHub issue 编号" }),
      branch_name: Type.Optional(
        Type.String({ description: "分支名，默认 feat/issue-{N}" }),
      ),
    }),

    async execute(_id, params, signal, onUpdate, ctx) {
      const n = params.issue_number;
      const branch = params.branch_name || `feat/issue-${n}`;
      const baseModel = resolveCoderModel(n);

      const defPath = findCoderAgentDef(ctx.cwd);
      if (!defPath) {
        return {
          content: [
            {
              type: "text",
              text: "❌ 找不到码农 agent 定义文件 (.pi/agents/coder.md)",
            },
          ],
          isError: true,
        };
      }

      const def = parseAgentDef(defPath);
      const model = def.model || baseModel;

      const upgraded =
        (reviewFailures.get(n) ?? 0) >= UPGRADE_THRESHOLD;
      const statusMsg = upgraded
        ? `🚀 启动码农处理 Issue #${n}（⚠️ 模型已升级: ${model}）...`
        : `🚀 启动码农处理 Issue #${n}（模型: ${model}）...`;

      onUpdate?.({
        content: [{ type: "text", text: statusMsg }],
      });

      const result = await runCoderProcess(
        ctx.cwd,
        n,
        branch,
        model,
        def.systemPrompt,
        signal,
        (msg) =>
          onUpdate?.({ content: [{ type: "text", text: msg }] }),
      );

      const header = result.success
        ? `✅ 码农完成 Issue #${result.issue} → PR #${result.pr}（${result.model}）`
        : `❌ 码农失败 Issue #${result.issue}（${result.model}）：${result.error}`;

      return {
        content: [{ type: "text", text: `${header}\n\n${result.output}` }],
        details: result,
        isError: !result.success,
      };
    },
  });

  // ══════════════════════════════════════════════════════
  // review_pr
  // ══════════════════════════════════════════════════════

  const REVIEW_CHECKLIST = [
    "### 回测可信度",
    "- [ ] 无未来函数：所有信号只用 as_of 及以前数据",
    "- [ ] 样本边界：样本外数据不泄露到样本内",
    "- [ ] T+1 时序：买入当日不检测退出",
    "- [ ] 退出优先级：结构止损 > 应急 > 时间 > 趋势 > 硬最大持仓",
    "- [ ] 双轨公平：唯一差异是主线过滤",
    "- [ ] 成本完整：买入佣金+滑点，卖出佣金+印花税+滑点",
    "- [ ] 参数可配置",
    "### 工程标准",
    "- [ ] 测试全绿",
    "- [ ] 新代码有测试",
    "- [ ] 分层架构",
    "- [ ] 输出协议合规",
    "### Agent 协作",
    "- [ ] PR 范围无夹带",
    "- [ ] Issue 完成度",
    "- [ ] ADR 一致",
    "- [ ] 研究免责声明",
    "- [ ] 幸存者偏差标注",
    "### 代码质量",
    "- [ ] 无占位符/fixture 残留",
    "- [ ] CSV utf-8-sig",
    "- [ ] 审计字段完整",
  ].join("\n");

  pi.registerTool({
    name: "review_pr",
    label: "Review PR",
    description: [
      "获取 PR diff 进行 review（action=review），批准（approve），",
      "要求修改（request_changes），或合并（merge）。",
      "review 时自动附加 checklist。",
    ].join(" "),
    promptSnippet: "获取 PR diff 或提交 review/合并",
    promptGuidelines: [
      "使用 review_pr 审查码农的 PR，对照 ADR-0003 的 checklist。",
      "review 通过后用 review_pr action=merge 合并。",
    ],
    parameters: Type.Object({
      pr_number: Type.Number({ description: "PR 编号" }),
      action: StringEnum(
        ["review", "approve", "request_changes", "merge"] as const,
        { description: "操作类型" },
      ),
      body: Type.Optional(
        Type.String({
          description: "review 评论（approve/request_changes 必填）",
        }),
      ),
    }),

    async execute(_id, params, _signal, _onUpdate, ctx) {
      const { pr_number: prNum, action, body } = params;

      try {
        // ── review: 获取 diff + 元数据 ──
        if (action === "review") {
          const [diffR, metaR] = await Promise.all([
            execCmd("gh", ["pr", "diff", String(prNum)], ctx.cwd),
            execCmd(
              "gh",
              [
                "pr",
                "view",
                String(prNum),
                "--json",
                "title,body,headRefName,additions,deletions,changedFiles,state",
              ],
              ctx.cwd,
            ),
          ]);

          if (diffR.code !== 0)
            throw new Error(`获取 diff 失败: ${diffR.stderr}`);

          const diff = diffR.stdout;
          const meta = metaR.code === 0 ? metaR.stdout : "{}";
          const truncatedDiff =
            diff.length > 50000
              ? diff.slice(0, 50000) +
                `\n\n[...截断，共 ${Buffer.byteLength(diff, "utf8")} 字节]`
              : diff;

          return {
            content: [
              {
                type: "text",
                text: `## PR #${prNum}\n\n${meta}\n\n## Diff\n\n${truncatedDiff}\n\n---\n请按以下 checklist review:\n${REVIEW_CHECKLIST}`,
              },
            ],
            details: {
              action,
              prNumber: prNum,
              diffLength: diff.length,
            },
          };
        }

        // ── approve / request_changes ──
        if (action === "approve" || action === "request_changes") {
          if (!body) {
            return {
              content: [
                { type: "text", text: "❌ approve/request_changes 需要 body 参数" },
              ],
              isError: true,
            };
          }

          const repo = await getRepo(ctx.cwd);
          const event =
            action === "approve" ? "APPROVE" : "REQUEST_CHANGES";
          const r = await execCmd(
            "gh",
            [
              "api",
              `repos/${repo}/pulls/${prNum}/reviews`,
              "-X",
              "POST",
              "--input",
              "-",
            ],
            ctx.cwd,
            JSON.stringify({ body, event }),
          );

          if (r.code !== 0)
            throw new Error(`提交 review 失败: ${r.stderr}`);

          // 更新 review 失败计数
          const issueNum = await getIssueFromPr(ctx.cwd, prNum);
          if (issueNum !== null) {
            if (action === "request_changes") {
              reviewFailures.set(
                issueNum,
                (reviewFailures.get(issueNum) ?? 0) + 1,
              );
            } else {
              reviewFailures.delete(issueNum);
            }
          }

          const icon = action === "approve" ? "✅" : "📝";
          const msg =
            action === "approve"
              ? `PR #${prNum} 已批准`
              : `PR #${prNum} 已要求修改`;
          return {
            content: [{ type: "text", text: `${icon} ${msg}` }],
          };
        }

        // ── merge ──
        if (action === "merge") {
          const r = await execCmd(
            "gh",
            ["pr", "merge", String(prNum), "--squash", "--delete-branch"],
            ctx.cwd,
          );
          if (r.code !== 0) throw new Error(`合并失败: ${r.stderr}`);

          // 重置 review 失败计数
          const issueNum = await getIssueFromPr(ctx.cwd, prNum);
          if (issueNum !== null) reviewFailures.delete(issueNum);

          return {
            content: [
              { type: "text", text: `🔀 PR #${prNum} 已合并（squash merge）` },
            ],
          };
        }

        return {
          content: [{ type: "text", text: `未知 action: ${action}` }],
          isError: true,
        };
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : String(err);
        return {
          content: [{ type: "text", text: `❌ ${message}` }],
          isError: true,
        };
      }
    },
  });
}
