import { beforeEach, describe, expect, it } from "vitest";
import {
  acknowledgeEdit,
  assertDraftScope,
  beginEdit,
  draft,
  editSnapshot,
  failEdit,
  observeRevision,
  resetEdits,
  saveLabel,
  tracked,
  undoAcknowledged,
} from "./edits";
const command = {
  path: "/analyses/a/materials/body",
  revision: 4,
  payload: {},
  method: "PUT",
};
beforeEach(() => resetEdits("a", 4));
describe("acknowledged session commands", () => {
  it("never labels a draft or pending write saved", () => {
    draft("material", true);
    expect(saveLabel(editSnapshot())).toContain("Unsaved");
    beginEdit(command);
    expect(saveLabel(editSnapshot())).toBe("Saving…");
    acknowledgeEdit(command, 5);
    expect(saveLabel(editSnapshot())).toContain("Unsaved");
    draft("material", false);
    expect(saveLabel(editSnapshot())).toBe("Saved · revision 5");
  });
  it("retains exact rejected command and clears unsafe undo after a conflict", () => {
    beginEdit(command);
    acknowledgeEdit(command, 5);
    const rejected = {
      ...command,
      revision: 5,
      payload: { material: "test draft" },
    };
    beginEdit(rejected);
    failEdit(rejected, true);
    expect(editSnapshot().pending).toEqual(rejected);
    expect(editSnapshot().history).toEqual([]);
    expect(saveLabel(editSnapshot())).toContain("Conflict");
  });
  it("keeps failed writes unacknowledged and does not add undo", () => {
    beginEdit(command);
    failEdit(command, false);
    expect(saveLabel(editSnapshot())).toContain("Save failed");
    expect(editSnapshot().revision).toBe(4);
    expect(editSnapshot().history).toEqual([]);
  });
  it("undoes commands with fresh head revisions and clears on context reset", () => {
    beginEdit(command);
    acknowledgeEdit(command, 5);
    const second = { ...command, revision: 5 };
    beginEdit(second);
    acknowledgeEdit(second, 6);
    undoAcknowledged(7);
    expect(editSnapshot().history).toEqual([4]);
    expect(editSnapshot().revision).toBe(7);
    resetEdits("b");
    acknowledgeEdit(second, 8);
    expect(editSnapshot().revision).toBe(0);
    expect(editSnapshot().history).toEqual([]);
  });
  it("limits undo to 50 commands and excludes previews, jobs and foreign writes", () => {
    for (let revision = 4; revision < 64; revision++) {
      const c = { ...command, revision };
      beginEdit(c);
      acknowledgeEdit(c, revision + 1);
    }
    expect(editSnapshot().history).toHaveLength(50);
    for (const path of [
      "/analyses/b/loads",
      "/analyses/a/direction-preview",
      "/analyses/a/mesh-controls/preview",
      "/analyses/a/restores",
      "/analyses/a/mesh-jobs",
      "/analyses/a/deck-exports",
    ])
      expect(tracked({ ...command, path })).toBe(false);
  });
  it("refuses unrelated writes that would discard another editor's draft", () => {
    draft("mesh", true);
    expect(() => assertDraftScope(command)).toThrow("other unsaved drafts");
    draft("mesh", false);
    draft("material", true);
    expect(() => assertDraftScope(command)).not.toThrow();
    expect(() =>
      assertDraftScope({
        ...command,
        path: "/analyses/a/display-units",
        method: "PATCH",
      }),
    ).not.toThrow();
  });
  it("new server heads invalidate undo without silently adopting a different revision", () => {
    beginEdit(command);
    acknowledgeEdit(command, 5);
    observeRevision("a", 6);
    expect(editSnapshot().phase).toBe("conflict");
    expect(editSnapshot().revision).toBe(5);
    expect(editSnapshot().history).toEqual([]);
  });
});
