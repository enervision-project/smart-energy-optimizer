package com.enervision.configuration;

import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Bootstrap for the module's slice tests ({@code @WebMvcTest}…): the real {@code Application} class lives in the
 * application module, which this module does not depend on.
 */
@SpringBootApplication
class ConfigurationTestApplication {
}
