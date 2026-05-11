/* CodeUp landing — single bundled entry point.
 *
 * Each landing/*.jsx file attaches its components to window in the order
 * they're imported below. app.jsx (last) renders the tree.
 *
 * React and ReactDOM are external — they're loaded as separate <script>
 * tags from /static/vendor/react/ in landing.html. This keeps the bundle
 * small and lets the browser cache React across page reloads.
 *
 * To rebuild: `npm run build` from the repo root.
 */
import "./tweaks-panel.jsx";
import "./editor-hero.jsx";
import "./hero.jsx";
import "./sonify.jsx";
import "./voice-ide.jsx";
import "./features.jsx";
import "./app.jsx";