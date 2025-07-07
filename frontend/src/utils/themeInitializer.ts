/**
 * Theme Initializer - Inicializa o tema na página
 */

export const initializeTheme = () => {
  // Carregar tema salvo do localStorage ou usar padrão
  const savedTheme = localStorage.getItem('presence-theme') || 'theme-pro';
  
  // Aplicar tema ao body
  applyTheme(savedTheme);
  
  return savedTheme;
};

export const applyTheme = (themeId: string) => {
  // Remover classes de tema existentes do body
  document.body.className = document.body.className.replace(/theme-\w+/g, '');
  // Adicionar nova classe de tema
  document.body.classList.add(themeId);
  
  // Aplicar ao elemento raiz também para máxima compatibilidade
  const root = document.documentElement;
  root.className = root.className.replace(/theme-\w+/g, '');
  root.classList.add(themeId);
  
  // Salvar no localStorage
  localStorage.setItem('presence-theme', themeId);
};

// Inicializar tema assim que o script carrega
if (typeof window !== 'undefined') {
  initializeTheme();
}