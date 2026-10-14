import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
type Theme = "light" | "dark";
const ThemeContext = createContext<Theme>("light");
export const useTheme = () => useContext(ThemeContext);
function initialTheme(): Theme {
  try {
    return localStorage.getItem("openfea-theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [error, setError] = useState("");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    const sync = (e: StorageEvent) => {
      if (e.key === "openfea-theme")
        setTheme(e.newValue === "dark" ? "dark" : "light");
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  return (
    <ThemeContext.Provider value={theme}>
      <div className="theme-control">
        <label>
          Theme
          <select
            value={theme}
            onChange={(e) => {
              const next = e.target.value as Theme;
              setTheme(next);
              setError("");
              try {
                localStorage.setItem("openfea-theme", next);
              } catch {
                setError(
                  "Theme applies for this visit; browser storage is unavailable.",
                );
              }
            }}
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        {error && <p role="status">{error}</p>}
      </div>
      {children}
    </ThemeContext.Provider>
  );
}
