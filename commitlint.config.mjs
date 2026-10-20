// Règles des messages de commit (Conventional Commits), volontairement souples :
// seuls le type et le sujet sont imposés, car semantic-release en a besoin.
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // scope libre (conseillé : le nom du service, ex. web, etl)
    'scope-enum': [0],
    'scope-case': [0],
    // sujets en français, souvent avec des noms propres (Angular, Docker…)
    'subject-case': [0],
    'subject-full-stop': [0],
    'header-max-length': [2, 'always', 120],
    // corps et pied libres (liens, tickets SEO-…)
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
    'body-leading-blank': [0],
    'footer-leading-blank': [0],
  },
};
