export type Tab = 'stats' | 'prompt' | 'history';

type NavbarProps = {
  active: Tab;
  onChange: (tab: Tab) => void;
};

const TABS: { id: Tab; label: string }[] = [
  { id: 'stats', label: 'Stats' },
  { id: 'prompt', label: 'Enter Prompt' },
  { id: 'history', label: 'History' },
];

function Navbar({ active, onChange }: NavbarProps) {
  return (
    <nav className="navbar">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          className={active === tab.id ? 'nav-item active' : 'nav-item'}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

export default Navbar;