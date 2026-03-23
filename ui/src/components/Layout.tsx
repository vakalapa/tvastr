import { Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

interface LayoutProps {
  children: ReactNode;
}

function Layout({ children }: LayoutProps) {
  const location = useLocation();

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-gray-700 bg-gray-950 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl font-bold text-purple-400">Tvastr</span>
          </Link>
          <p className="text-xs text-gray-500 mt-1">Autonomous Code Forge</p>
        </div>

        <nav className="flex-1 p-4">
          <ul className="space-y-1">
            <li>
              <Link
                to="/"
                className={`block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  location.pathname === "/"
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
              >
                Dashboard
              </Link>
            </li>
          </ul>
        </nav>

        <div className="p-4 border-t border-gray-700 text-xs text-gray-600">
          v0.1.0
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  );
}

export default Layout;
