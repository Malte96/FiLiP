import unittest

from filip.semantics.entity_model_generator import generate_vocabulary_models
from filip.semantics.vocabulary_configurator import VocabularyConfigurator


class TestSemanticModels(unittest.TestCase):

    def test_1_model_creation(self):
        vocabulary = VocabularyConfigurator.create_vocabulary()

        vocabulary = \
            VocabularyConfigurator.add_ontology_to_vocabulary_as_file(
                vocabulary=vocabulary,
                path_to_file='./ontology_files/ParsingTesterOntology.ttl')

        generate_vocabulary_models(vocabulary, "./", "models")

    def test_2_model_relation_validation(self):
        from models import Class1, Class13, Class2, Class4, Class123, Individual1

        class1 = Class1()
        class13 = Class13()

        # check for correct rules
        self.assertEqual(class1.oProp1.rule, "some (Class2 or Class4)")
        self.assertEqual(class13.objProp2.rule,
               "some Class1, value Individual1, some (Class1 and Class2)")

        # test simple rule
        self.assertFalse(class1.oProp1.validate())
        class1.oProp1.append(Class2())
        self.assertTrue(class1.oProp1.validate())
        class1.oProp1.append(Class4())
        self.assertTrue(class1.oProp1.validate())
        class1.oProp1.append(Class123())
        self.assertTrue(class1.oProp1.validate())

        # test complex rule
        self.assertFalse(class13.objProp2.validate())
        class13.objProp2.append(class1)
        self.assertFalse(class13.objProp2.validate())
        class13.objProp2.append(Class123())
        self.assertFalse(class13.objProp2.validate())
        del class13.objProp2[1]
        class13.objProp2.append(Individual1())
        self.assertTrue(class13.objProp2.validate())





