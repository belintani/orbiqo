import { describe, expect, it } from "vitest";
import { workspaceContext } from "../client/src/lib/workspaceContext";

describe("workspace context", () => {
  it("gives every non-creation workspace a distinct task-oriented orientation", () => {
    expect(Object.keys(workspaceContext)).toEqual(["read", "compare", "benchmarks", "renderer"]);
    expect(workspaceContext.read.body).toContain("local");
    expect(workspaceContext.compare.body).toContain("four real toolchains");
    expect(workspaceContext.benchmarks.body).toContain("not as a universal winner ranking");
    expect(workspaceContext.renderer.body).toContain("renderer optimization");
  });
});
