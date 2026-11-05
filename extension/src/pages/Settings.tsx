import { useEffect, useState } from "react";
import { DEFAULT_PREFERENCES, loadPreferences, savePreferences, type UserPreferences } from "../settings";

export default function Settings() {
  const [preferences, setPreferences] = useState<UserPreferences>(DEFAULT_PREFERENCES);
  const [isLoaded, setIsLoaded] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");

  useEffect(() => {
    loadPreferences()
      .then(setPreferences)
      .catch(() => setSaveMessage("Could not load preferences from extension storage."))
      .finally(() => setIsLoaded(true));
  }, []);

  async function updatePreferences(next: UserPreferences) {
    setPreferences(next);
    setSaveMessage("");
    try {
      await savePreferences(next);
      setSaveMessage("Preferences saved.");
    } catch {
      setSaveMessage("Could not save preferences.");
    }
  }

  return (
    <main className="Board1 settings-page">
      <h2>Settings</h2>
      {!isLoaded ? <p role="status">Loading preferences…</p> : <>
        <section className="settings-section">
          <label htmlFor="validator-score">Validator acceptance score</label>
          <p>Choose the minimum score a rewrite must receive to be accepted. Higher scores are stricter.</p>
          <select
            id="validator-score"
            value={preferences.validatorPassScore ?? "auto"}
            onChange={(event) => void updatePreferences({
              ...preferences,
              validatorPassScore: event.target.value === "auto" ? null : Number(event.target.value),
            })}
          >
            <option value="auto">Automatic by prompt type</option>
            {Array.from({ length: 10 }, (_, index) => index + 1).map((score) => (
              <option value={score} key={score}>{score} / 10</option>
            ))}
          </select>
        </section>

        <section className="settings-section">
          <label htmlFor="rewrite-attempts">Maximum rewrite attempts</label>
          <p>Each attempt may call the optimizer and validator. More attempts can improve the result, but may take longer.</p>
          <select
            id="rewrite-attempts"
            value={preferences.maxOptimizationAttempts}
            onChange={(event) => void updatePreferences({
              ...preferences,
              maxOptimizationAttempts: Number(event.target.value),
            })}
          >
            {[1, 2, 3, 4, 5].map((attempts) => (
              <option value={attempts} key={attempts}>{attempts} {attempts === 1 ? "attempt" : "attempts"}</option>
            ))}
          </select>
        </section>
        <p className="settings-save-message" role="status">{saveMessage}</p>
      </>}
    </main>
  );
}
