from nltk.tokenize.treebank import TreebankWordDetokenizer
from nltk.tokenize import wordpunct_tokenize
from transformers import MT5ForConditionalGeneration, T5Tokenizer


class MyModel():
    def __init__(self):
        # do here any initializations you require

        self.DIAC_MAP = {'ț': 't', 'ș': 's', 'Ț': 'T', 'Ș': 'S',
                         'Ă': 'A', 'ă': 'a', 'Â': 'A', 'â': 'a', 'Î': 'I', 'î': 'i'}

        self.GENERATE_DIAC_MAP = {'t': ['t', 'ț'], 's': ['s', 'ș'], 'T': ['T', 'Ț'], 'S': [
            'S', 'Ș'], 'A': ['A', 'Ă', 'Â'], 'a': ['a', 'ă', 'â'], 'I': ['I', 'Î'], 'i': ['i', 'î']}

        self.fine_tune_diacrit_dict = {}  # Mandatory diacritics exchanges dictionary

        # Found words over the statistical threshhold
        self.known_mandatory_diacritics_set = []

    def remove_diacritics_prop(self, prop):
        for diac in self.DIAC_MAP:
            prop = prop.replace(diac, self.DIAC_MAP[diac])

        return prop

    # Banned list allows not to generate diacritics permutations on specific letters
    def generate_word_diacritics_perms(self, original_word, crt_length, generated_permutations, banned_list):
        if crt_length == len(original_word):
            return generated_permutations

        # check if the length is zero
        if crt_length == 0:
            generated_permutations = [""]

        # define the brute letter
        original_letter = original_word[crt_length]

        new_generated_permutations = []

        # if we want to generte a permutation for a letter but we do not want to be in the banned list,
        # but for this we want to forck the tree undeterministically
        if original_letter in self.GENERATE_DIAC_MAP.keys() and original_letter not in banned_list:
            diacritics_for_letter = self.GENERATE_DIAC_MAP[original_letter]

            for word in generated_permutations:
                for diacrit in diacritics_for_letter:
                    new_generated_permutations.append(word + diacrit)
        # otherwise insert a new letter to all current permutations
        else:
            for word in generated_permutations:
                new_generated_permutations.append(word + original_letter)

        generated_permutations = new_generated_permutations

        return self.generate_word_diacritics_perms(original_word, crt_length+1, generated_permutations, banned_list)

    # populates the fine-tune dictionary based on the sets of letters that goes more than the threshhold
    def populate_finetune_dict(self):
        for word in self.known_mandatory_diacritics_set:
            stripped_word = self.remove_diacritics_prop(word)
            diacrit_perms = self.generate_word_diacritics_perms(
                stripped_word, 0, [], [])

            for perm in diacrit_perms:
                self.fine_tune_diacrit_dict[perm] = word

        return

    # It receives the output from your transformer, and on top of it, it makes the appropriate in-place replacements
    def mandatory_diacritics(self, original_sentence):
        tokenized_sentence = wordpunct_tokenize(original_sentence)

        # searching the mandatory enter for the current token and returns it in its place
        for i in range(len(tokenized_sentence)):
            crt_token = tokenized_sentence[i]

            if crt_token in self.fine_tune_diacrit_dict:
                tokenized_sentence[i] = self.fine_tune_diacrit_dict[crt_token]

        return TreebankWordDetokenizer().detokenize(tokenized_sentence).replace(" .", ".")

    def load(self, model_resource_folder):
        # we'll call this code before prediction
        # use this function to load any pretrained model and any other resource, from the given folder path
        self.model = MT5ForConditionalGeneration.from_pretrained(
            'iliemihai/mt5-base-romanian-diacritics')

        self.tokenizer = T5Tokenizer.from_pretrained(
            'iliemihai/mt5-base-romanian-diacritics')

    # *** OPTIONAL ***
    def train(self, train_data_file, validation_data_file, model_resource_folder):
        cuv = dict()

        for el in train_data_file:
            list_of_words = "".join((char if char.isalpha() else " ")
                                    for char in el["text"]).split()

            if (len(list_of_words) < 1):
                continue

            list_of_words[0] = list_of_words[0].lower()

            for word in list_of_words:
                word_no_diac = word

                for diac in self.DIAC_MAP:
                    word_no_diac = word_no_diac.replace(
                        diac, self.DIAC_MAP[diac])

                if(word_no_diac in cuv):
                    if(len([item for item in cuv[word_no_diac] if item[0] == word]) == 0):
                        cuv[word_no_diac].append((word, 1))
                    else:
                        el = [item for item in cuv[word_no_diac] if item[0] == word][0]
                        nr = el[1]
                        cuv[word_no_diac].remove(el)
                        nr = nr+1
                        new_el = (word, nr)
                        cuv[word_no_diac].append(new_el)
                else:
                    cuv[word_no_diac] = [(word, 1)]

        # calculate the probabilities for every word and if one word appears with more than 95% then we only keep that version of the word
        for el in cuv:
            sum = 0

            for element in cuv[el]:
                sum = sum + element[1]

            for element in cuv[el]:
                if(element[1] >= 0.95*sum):
                    cuv[el] = [(element[0], 1)]
        resultList = list(cuv.items())

        final = set()

        for el in cuv:
            if(len(cuv[el]) == 1):
                word = cuv[el][0][0]
                final.add(word)
                final.add(word.capitalize())

        self.known_mandatory_diacritics_set = final
        self.populate_finetune_dict()

        # we'll call this function right after init
        # place here all your training code
        # at the end of training, place all required resources, trained model, etc in the given model_resource_folder
        return

    def predict(self, input_file, output_file):
        # we'll call this function after the load()
        # use this place to run the prediction
        # the input is a file that does not contain diacritics
        # the output is a file that contains diacritics and,
        #    **is identical at character level** with the input file,
        #   excepting replaced diacritic letters
        final_output = ""
        
        with open(input_file, "r") as f:
            for line in f:
                inputs = self.tokenizer(
                    line, max_length=256, truncation=True, return_tensors="pt")
                outputs = self.model.generate(
                    input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"])
                output = self.tokenizer.decode(
                    outputs[0], skip_special_tokens=True)
                output = self.mandatory_diacritics(output).strip()
                final_output += f'{output}\n'

        with open(output_file, "w") as f:
            f.write(final_output)
