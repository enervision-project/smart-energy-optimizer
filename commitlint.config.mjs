// Deliberately loose: only type and subject are enforced, as semantic-release needs them.
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // free scope (suggested: the service name, e.g. web, etl)
    'scope-enum': [0],
    'scope-case': [0],
    // French subjects, often with proper nouns (Angular, Docker…)
    'subject-case': [0],
    'subject-full-stop': [0],
    'header-max-length': [2, 'always', 120],
    // free body and footer (links, SEO-… tickets)
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
    'body-leading-blank': [0],
    'footer-leading-blank': [0],
  },
};
